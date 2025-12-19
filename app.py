import os
import time
import re
import logging
import json
from flask import Flask, request, jsonify, render_template_string, render_template, redirect, url_for, send_from_directory, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
from flask_migrate import Migrate
import requests
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from requests.exceptions import RequestException, Timeout

basedir = os.path.abspath(os.path.dirname(__file__))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración desde variables de entorno (con valores por defecto para desarrollo)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URI',
    """mssql+pyodbc://sa:SisteNob+25@172.16.1.200/encuestador?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"""
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Verifica conexiones antes de usarlas
    'pool_recycle': 3600,   # Recicla conexiones cada hora
    'pool_size': 10,
    'max_overflow': 20
}
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp-mail.outlook.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'soporte@nobis.com.ar')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'Noj47222')

db = SQLAlchemy(app)
mail = Mail(app)
migrate = Migrate(app, db)

# Configuración
PER_PAGE = int(os.getenv('PER_PAGE', 100))
TOKEN = os.getenv('API_TOKEN', "uqdXYUb4k6AmcFtDOfzoPpdSTykiXPhxLe8UEpiyXtUJHw3ipa4klPhjmpwemgaT")
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 30))
LAST_PAGE_FILES = {
    "tickets": "paginas/last_page_tickets.txt",
    "users": "paginas/last_page_users.txt"
}

# Mapeo de agentes (debería estar en BD, pero por ahora se mantiene aquí)
AGENTES_MAP = {
    10787: 'Juan Cuevas',
    7211: 'Agustin Jimenez',
    5922: 'Agustin Jimenez',
    8506: 'Valentina Martinelli',
    3733: 'Lazaro Gonzalez',
    6859: 'Lazaro Gonzalez',
    33: 'Nahuel Saracho',
    6716: 'Nahuel Saracho',
    12066: 'Iara Zalazar',
    13833: 'Guillermina Caceres'
}

# Blacklist de emails
BLACKLIST_EMAILS = {
    'nahuel.saracho@nobis.com.ar',
    'nsaracho@nobissalud.com.ar',
    'lbgonzalez@nobissalud.com.ar',
    'lazaro.gonzalez@nobis.com.ar',
    'agustin.jimenez@nobis.com.ar',
    'juan.cuevas@nobis.com.ar',
    'iara.zalazar@nobis.com.ar',
    'guillermina.caceres@nobis.com.ar'
}

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    organization_id = db.Column(db.Integer, nullable=True)
    login = db.Column(db.String(100), nullable=False, unique=True)
    firstname = db.Column(db.String(100))
    email = db.Column(db.String(100), nullable=False)

class Gestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer)
    priority_id = db.Column(db.Integer)
    state_id = db.Column(db.Integer)
    organization_id = db.Column(db.Integer)
    number = db.Column(db.String)
    title = db.Column(db.String)
    owner_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    first_response_at = db.Column(db.Text)
    close_at = db.Column(db.Text)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    created_at = db.Column(db.Text)
    updated_at = db.Column(db.Text)
    type = db.Column(db.String)
    category = db.Column(db.String)
    level = db.Column(db.String)
    estado_enviado = db.Column(db.Boolean, default=False)

class Respuesta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gestion_id = db.Column(db.Integer, db.ForeignKey('gestion.id'), nullable=False)
    nivel = db.Column(db.String(10), nullable=True)
    comentarios = db.Column(db.Text, nullable=True)
    cliente = db.Column(db.String(100), nullable=False)
    promedio_respuestas = db.Column(db.String(10), nullable=False)
    porcentaje_respuestas = db.Column(db.Float, nullable=False)
    fecha_respuesta = db.Column(db.DateTime, nullable=False)
    agente_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    agente_nombre = db.Column(db.String(150), nullable=False)

    detalles = db.relationship("RespuestaDetalle", backref="respuesta", lazy=True)


class RespuestaDetalle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    respuesta_id = db.Column(db.Integer, db.ForeignKey('respuesta.id'), nullable=False)
    nivel = db.Column(db.String(10), nullable=True)
    pregunta = db.Column(db.String(50), nullable=False)  # "Primera", "Segunda", etc.
    valor = db.Column(db.Integer, nullable=False)  # El valor de la respuesta


class ExecutionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_ejecucion = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    nuevas_gestiones=db.Column(db.Integer, nullable=False)
    nuevos_usuarios=db.Column(db.Integer, nullable=False)

# Función para convertir timedelta en días, horas y minutos
def format_timedelta(td):
    dias = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if dias > 1:
        return f"{dias} dias, {hours} horas, {minutes} minutos"
    elif dias == 1:
        return f"{dias} dia, {hours} horas, {minutes} minutos"
    else:
        return f"{hours} horas, {minutes} minutos"


def enviar_encuesta(gestion, intentos=3, retraso_reintento=5):
    """Envía una encuesta por email con manejo de errores y reintentos."""
    with app.app_context():
        # Verificar si ya fue enviada
        if gestion.estado_enviado:
            logger.info(f"Gestión {gestion.id} ya fue enviada. No se enviará de nuevo.")
            return True

        # Validar que la gestión tenga created_by_id
        if not gestion.created_by_id:
            logger.error(f"Gestión {gestion.id} no tiene created_by_id")
            return False

        for intento in range(intentos):
            try:
                # Obtener el usuario relacionado con la gestión
                usuario = db.session.get(Usuario, gestion.created_by_id)
                if not usuario:
                    logger.error(f"No se encontró un usuario con id {gestion.created_by_id}")
                    return False

                # Validar email del usuario
                if not usuario.email or not isinstance(usuario.email, str):
                    logger.error(f"Usuario {usuario.id} no tiene un email válido")
                    return False

                # Renderizar el template con contenido dinámico
                try:
                    cuerpo_mensaje = render_template(
                        'index.html',
                        gestion_id=gestion.id,
                        gestion_numero=gestion.number,
                        gestion_title=gestion.title
                    )
                except Exception as e:
                    logger.error(f"Error al renderizar template para gestión {gestion.id}: {e}")
                    return False

                # Configurar y enviar el mensaje
                msg = Message(
                    'Encuesta de Satisfacción',
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[usuario.email],
                    html=cuerpo_mensaje
                )

                mail.send(msg)
                logger.info(f"Encuesta enviada exitosamente a {usuario.email} para gestión {gestion.id}")

                # Actualizar estado de la gestión
                try:
                    gestion.estado_enviado = True
                    db.session.commit()
                    return True
                except SQLAlchemyError as e:
                    logger.error(f"Error al actualizar estado de gestión {gestion.id}: {e}")
                    db.session.rollback()
                    return False

            except Exception as e:
                logger.warning(f"Error al enviar encuesta (intento {intento + 1}/{intentos}) para gestión {gestion.id}: {e}")
                if intento < intentos - 1:
                    logger.info(f"Reintentando en {retraso_reintento} segundos...")
                    time.sleep(retraso_reintento)
                else:
                    logger.error(f"No se pudo enviar la encuesta para la gestión {gestion.id} después de {intentos} intentos.")
                    return False
        
        return False
                

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')


def verificar_y_enviar_encuestas():
    """Verifica y envía encuestas pendientes con manejo de errores mejorado."""
    with app.app_context():
        try:
            gestiones_pendientes = Gestion.query.filter_by(estado_enviado=False).all()
            logger.info(f"Gestiones pendientes encontradas: {len(gestiones_pendientes)}")

            count_exitosos = 0
            count_fallidos = 0
            
            for gestion in gestiones_pendientes:
                try:
                    if enviar_encuesta(gestion):
                        count_exitosos += 1
                    else:
                        count_fallidos += 1
                    # Pequeña pausa para no sobrecargar el servidor de email
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error inesperado al procesar gestión {gestion.id}: {e}")
                    count_fallidos += 1
                    continue

            logger.info(f"Proceso completado: {count_exitosos} exitosos, {count_fallidos} fallidos")
            return {"exitosos": count_exitosos, "fallidos": count_fallidos}
            
        except SQLAlchemyError as e:
            logger.error(f"Error de base de datos en verificar_y_enviar_encuestas: {e}")
            db.session.rollback()
            raise
        except Exception as e:
            logger.error(f"Error inesperado en verificar_y_enviar_encuestas: {e}")
            raise
        
# Definir la zona horaria de Buenos Aires
zona_horaria = timezone(timedelta(hours=-3))

@app.route('/procesar-encuesta', methods=['POST'])
def procesar_encuesta():
    """Procesa una encuesta recibida con validaciones mejoradas."""
    try:
        datos = request.form
        logger.info(f"Datos de encuesta recibidos para gestión: {datos.get('gestion_id')}")

        # Validar gestion_id
        gestion_id = datos.get('gestion_id')
        if not gestion_id:
            logger.warning("gestion_id no recibido en la petición")
            return jsonify({"status": "error", "message": "gestion_id es requerido"}), 400

        try:
            gestion_id = int(gestion_id)
        except (ValueError, TypeError):
            logger.warning(f"gestion_id inválido: {datos.get('gestion_id')}")
            return jsonify({"status": "error", "message": "gestion_id debe ser un número válido"}), 400

        # Verificar si ya existe una respuesta
        respuesta_existente = Respuesta.query.filter_by(gestion_id=gestion_id).first()
        if respuesta_existente:
            logger.warning(f"Ya existe una respuesta para el ticket {gestion_id}")
            return jsonify({
                "status": "error",
                "message": f"Ya existe una respuesta para el ticket {gestion_id}."
            }), 400

        # Validar que la gestión existe
        gestion = db.session.get(Gestion, gestion_id)
        if not gestion:
            logger.error(f"Gestión {gestion_id} no encontrada")
            return jsonify({"status": "error", "message": f"Gestión {gestion_id} no encontrada"}), 404

        # Validar que existe el agente
        if not gestion.owner_id:
            logger.error(f"Gestión {gestion_id} no tiene owner_id")
            return jsonify({"status": "error", "message": "La gestión no tiene un agente asignado"}), 400

        usuario_age = db.session.get(Usuario, gestion.owner_id)
        if not usuario_age:
            logger.error(f"Usuario agente {gestion.owner_id} no encontrado")
            return jsonify({"status": "error", "message": "Agente no encontrado"}), 404

        # Obtener nivel y comentarios
        nivel_g = datos.get('nivel')
        comentarios = datos.get('comentarios', '')

        # Extraer y validar respuestas del formulario
        respuestas = {}
        preguntas_validas = ["Primera", "Segunda", "Tercera", "Cuarta"]
        
        for pregunta in preguntas_validas:
            valor_str = datos.get(pregunta.lower(), None)
            if valor_str:
                try:
                    valor = int(valor_str)
                    if 1 <= valor <= 3:  # Validar rango
                        respuestas[pregunta] = valor
                    else:
                        logger.warning(f"Valor fuera de rango para {pregunta}: {valor}")
                except (ValueError, TypeError):
                    logger.warning(f"Valor inválido para {pregunta}: {valor_str}")

        if not respuestas:
            logger.warning(f"No hay respuestas válidas para gestión {gestion_id}")
            return jsonify({"status": "error", "message": "Debe proporcionar al menos una respuesta válida"}), 400

        # Calcular puntajes
        puntaje_total = sum(respuestas.values())
        puntaje_maximo = len(respuestas) * 3
        promedio_respuestas = f"{puntaje_total}/{puntaje_maximo}"
        porcentaje = round((puntaje_total / puntaje_maximo) * 100, 2)

        # Obtener fecha actual en Buenos Aires
        respuesta_time = datetime.now(zona_horaria)

        # Obtener nombre del agente del mapeo
        age_nombre = AGENTES_MAP.get(usuario_age.id, 'Desconocido')

        # Crear la respuesta principal
        nueva_respuesta = Respuesta(
            gestion_id=gestion_id,
            nivel=nivel_g,
            comentarios=comentarios,
            cliente=datos.get('cliente', ''),
            promedio_respuestas=promedio_respuestas,
            porcentaje_respuestas=porcentaje,
            fecha_respuesta=respuesta_time,
            agente_id=usuario_age.id,
            agente_nombre=age_nombre
        )
        
        try:
            db.session.add(nueva_respuesta)
            db.session.flush()  # Obtener el ID sin commit

            # Guardar respuestas individuales
            detalles = [
                RespuestaDetalle(
                    respuesta_id=nueva_respuesta.id,
                    nivel=nivel_g,
                    pregunta=preg,
                    valor=valor
                )
                for preg, valor in respuestas.items()
            ]
            db.session.add_all(detalles)
            db.session.commit()
            
            logger.info(f"Encuesta procesada exitosamente para gestión {gestion_id}")
            return redirect(url_for('gracias'))

        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Error de integridad al guardar respuesta para gestión {gestion_id}: {e}")
            return jsonify({"status": "error", "message": "Error al guardar la respuesta"}), 500
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error de base de datos al procesar encuesta: {e}")
            return jsonify({"status": "error", "message": "Error al guardar en la base de datos"}), 500

    except ValueError as e:
        logger.error(f"Error de validación: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"Error inesperado al procesar encuesta: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"status": "error", "message": "Error interno del servidor"}), 500


@app.route('/gracias')
def gracias():
    return render_template('gracias.html')


@app.route('/encuesta/<int:gestion_id>')
def mostrar_encuesta(gestion_id):
    """Muestra la encuesta para una gestión específica con manejo de errores mejorado."""
    try:
        gestion = Gestion.query.get_or_404(gestion_id)

        # Seleccionar el template según el nivel
        nivel_templates = {
            "Nivel 1": 'nivel_uno.html',
            "Nivel 2": 'nivel_dos.html',
            "Nivel 3": 'nivel_tres.html'
        }
        template_name = nivel_templates.get(gestion.level, 'nivel_uno.html')
        
        if gestion.level not in nivel_templates:
            logger.warning(f"Nivel desconocido para gestión {gestion_id}: {gestion.level}")

        # Calcular las diferencias de tiempo con manejo de errores
        try:
            if not gestion.created_at:
                logger.error(f"Gestión {gestion_id} no tiene created_at")
                return jsonify({"status": "error", "message": "Datos de gestión incompletos"}), 400

            created_at_date = datetime.strptime(gestion.created_at, '%Y-%m-%dT%H:%M:%S.%fZ')
        except (ValueError, TypeError) as e:
            logger.error(f"Error al parsear created_at para gestión {gestion_id}: {e}")
            return jsonify({"status": "error", "message": "Error al procesar fechas de la gestión"}), 500
        
        try:
            if gestion.first_response_at:
                first_response_date = datetime.strptime(gestion.first_response_at, '%Y-%m-%dT%H:%M:%S.%fZ')
            else:
                first_response_date = created_at_date
        except (ValueError, TypeError) as e:
            logger.warning(f"Error al parsear first_response_at para gestión {gestion_id}: {e}")
            first_response_date = created_at_date
        
        try:
            if gestion.close_at:
                close_at_date = datetime.strptime(gestion.close_at, '%Y-%m-%dT%H:%M:%S.%fZ')
            else:
                close_at_date = first_response_date
        except (ValueError, TypeError) as e:
            logger.warning(f"Error al parsear close_at para gestión {gestion_id}: {e}")
            close_at_date = first_response_date

        # Calcular diferencias
        creado_a_firstresponse = first_response_date - created_at_date
        first_closed = close_at_date - first_response_date

        primer_dif = format_timedelta(creado_a_firstresponse)
        seg_dif = format_timedelta(first_closed)

        # Renderizar el template
        return render_template(
            template_name,
            gestion_id=gestion.id,
            titulo=gestion.title or 'Sin título',
            level=gestion.level or 'Nivel 1',
            created_by_id=gestion.created_by_id,
            primer_dif=primer_dif,
            seg_dif=seg_dif
        )
    
    except Exception as e:
        logger.error(f"Error inesperado en mostrar_encuesta para gestión {gestion_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Error al cargar la encuesta"}), 500


@app.route('/verificar-y-enviar-encuestas', methods=['GET'])
def trigger_verificar_y_enviar_encuestas():
    """Endpoint para disparar manualmente el envío de encuestas.
    Redirige a la página de progreso para ver el proceso en tiempo real.
    """
    return redirect(url_for('progreso_enviar_encuestas'))


@app.route('/progreso-enviar-encuestas')
def progreso_enviar_encuestas():
    """Página HTML para mostrar el progreso del envío de encuestas."""
    return render_template('progreso_enviar.html', titulo="Envío de Encuestas")


@app.route('/stream-enviar-encuestas')
def stream_enviar_encuestas():
    """Endpoint SSE para streaming del progreso de envío de encuestas."""
    def generate():
        def progress_callback(tipo, mensaje, porcentaje):
            data = {
                "tipo": tipo,
                "mensaje": mensaje,
                "porcentaje": porcentaje,
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(data)}\n\n"
        
        try:
            # Enviar evento inicial
            yield f"data: {json.dumps({'tipo': 'start', 'mensaje': 'Iniciando proceso...', 'porcentaje': 0})}\n\n"
            
            # Ejecutar función con callback
            resultado = verificar_y_enviar_encuestas(progress_callback=progress_callback)
            
            # Enviar evento final
            yield f"data: {json.dumps({'tipo': 'end', 'mensaje': 'Proceso completado', 'resultado': resultado, 'porcentaje': 100})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'tipo': 'error', 'mensaje': f'Error: {str(e)}', 'porcentaje': 0})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/test-email')
def test_email():
    try:
        msg = Message('Test Email',
                      sender=app.config['MAIL_USERNAME'],
                      recipients=['lazaro.gonzalez@nobis.com.ar'])
        msg.body = "Email de prueba."
        mail.send(msg)
        return "Email sent successfully!"
    except Exception as e:
        return f"Error sending email: {str(e)}"


@app.route('/ver-gestiones')
def ver_gestiones():
    """Lista todas las gestiones con paginación para evitar cargar demasiados datos."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)  # Máximo 100 por página
        
        pagination = Gestion.query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        return jsonify({
            'gestiones': [{
                'id': g.id,
                'encuesta_enviada': g.estado_enviado
            } for g in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })
    except Exception as e:
        logger.error(f"Error en ver_gestiones: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Error al obtener gestiones"}), 500


# Insertar Usuarios y gestiones
def get_last_page(endpoint, default=1):
    """Obtiene la última página procesada desde archivo con manejo de errores."""
    last_page_file = LAST_PAGE_FILES.get(endpoint)
    if not last_page_file:
        return default
    
    try:
        if os.path.exists(last_page_file):
            with open(last_page_file, "r") as file:
                contenido = file.read().strip()
                if contenido:
                    return int(contenido)
    except (ValueError, IOError) as e:
        logger.warning(f"Error al leer last_page para {endpoint}: {e}")
    
    return default

def save_last_page(endpoint, page):
    """Guarda la última página procesada con manejo de errores."""
    last_page_file = LAST_PAGE_FILES.get(endpoint)
    if not last_page_file:
        return
    
    try:
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(last_page_file), exist_ok=True)
        with open(last_page_file, "w") as file:
            file.write(str(page))
    except IOError as e:
        logger.error(f"Error al guardar last_page para {endpoint}: {e}")

def insertar_gestiones(registros):
    """Inserta gestiones nuevas con validaciones mejoradas y batch processing."""
    nuevos_registros = 0
    gestiones_a_insertar = []
    
    # Obtener IDs existentes en una sola consulta para evitar N+1
    ids_existentes = {g.id for g in Gestion.query.with_entities(Gestion.id).all()}
    
    # Obtener todos los usuarios necesarios en una sola consulta
    user_ids = set()
    for gestion in registros:
        user_ids.add(gestion.get("created_by_id"))
        user_ids.add(gestion.get("updated_by_id"))
    
    usuarios_map = {u.id: u for u in Usuario.query.filter(Usuario.id.in_(user_ids)).all()}
    
    for gestion in registros:
        try:
            gestion_id = gestion.get("id")
            if not gestion_id or gestion_id in ids_existentes:
                continue

            # Validar campos requeridos
            if not gestion.get("created_at"):
                logger.warning(f"Gestión sin created_at: {gestion_id}")
                continue

            try:
                created_at_date = datetime.strptime(gestion.get("created_at"), '%Y-%m-%dT%H:%M:%S.%fZ')
            except (ValueError, TypeError) as e:
                logger.warning(f"Error al parsear fecha para gestión {gestion_id}: {e}")
                continue

            # Obtener usuarios del mapa
            usuario = usuarios_map.get(gestion.get("created_by_id"))
            usuario2 = usuarios_map.get(gestion.get("updated_by_id"))

            if not usuario:
                logger.warning(f"No se encontró usuario con id {gestion.get('created_by_id')}")
                continue

            # Validar email
            if not usuario.email:
                logger.debug(f"Usuario {usuario.id} no tiene email")
                continue

            # Verificar validez del email
            validez = False
            if (re.search(r"@(nobis|nobissalud)\.com(\.ar)?$", usuario.email) and 
                usuario.email != 'soporte@nobis.com.ar' and 
                usuario2 and usuario2.email != usuario.email and 
                usuario.email not in BLACKLIST_EMAILS):
                validez = True

            # Validar condiciones para insertar
            if (gestion.get("state_id") == 4 and 
                gestion.get("group_id") == 13 and 
                created_at_date >= datetime(2025, 1, 1) and 
                validez):
                
                nueva_gestion = Gestion(
                    id=gestion_id,
                    group_id=gestion.get("group_id"),
                    priority_id=gestion.get("priority_id"),
                    state_id=gestion.get("state_id"),
                    number=gestion.get("number"),
                    title=gestion.get("title"),
                    owner_id=gestion.get("owner_id"),
                    customer_id=gestion.get("customer_id"),
                    first_response_at=gestion.get("first_response_at"),
                    close_at=gestion.get("close_at"),
                    updated_by_id=gestion.get("updated_by_id"),
                    created_by_id=gestion.get("created_by_id"),
                    created_at=gestion.get("created_at"),
                    updated_at=gestion.get("updated_at"),
                    type=gestion.get("type"),
                    category=gestion.get("category"),
                    level=gestion.get("niveles")
                )
                gestiones_a_insertar.append(nueva_gestion)
                nuevos_registros += 1
                logger.debug(f"Nueva gestión preparada: {gestion_id} - {usuario.email}")

        except Exception as e:
            logger.error(f"Error al procesar gestión {gestion.get('id')}: {e}")
            continue

    # Insertar en batch
    if gestiones_a_insertar:
        try:
            db.session.add_all(gestiones_a_insertar)
            db.session.commit()
            logger.info(f"Insertadas {nuevos_registros} nuevas gestiones")
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Error de integridad al insertar gestiones: {e}")
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error de BD al insertar gestiones: {e}")
            raise

    return nuevos_registros


def insertar_usuarios(registros):
    """Inserta usuarios nuevos con validaciones mejoradas y batch processing."""
    nuevos_registros = 0
    usuarios_a_insertar = []
    
    # Obtener IDs existentes en una sola consulta
    ids_existentes = {u.id for u in Usuario.query.with_entities(Usuario.id).all()}
    
    for usuario in registros:
        try:
            usuario_id = usuario.get("id")
            if not usuario_id or usuario_id in ids_existentes:
                continue

            # Validar longitud de los campos
            login = usuario.get("login")
            firstname = usuario.get("firstname")
            email = usuario.get("email")

            if any(len(campo or "") > 100 for campo in [login, firstname, email]):
                logger.debug(f"Usuario {usuario_id} omitido: campo excede 100 caracteres")
                continue

            # Validar campos requeridos
            if not login or not email:
                logger.debug(f"Usuario {usuario_id} omitido: falta login o email")
                continue

            nuevo_usuario = Usuario(
                id=usuario_id,
                organization_id=usuario.get("organization_id"),
                login=login,
                firstname=firstname,
                email=email,
            )
            usuarios_a_insertar.append(nuevo_usuario)
            nuevos_registros += 1

        except Exception as e:
            logger.error(f"Error al procesar usuario {usuario.get('id')}: {e}")
            continue

    # Insertar en batch
    if usuarios_a_insertar:
        try:
            db.session.add_all(usuarios_a_insertar)
            db.session.commit()
            logger.info(f"Insertados {nuevos_registros} nuevos usuarios")
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Error de integridad al insertar usuarios: {e}")
            # Intentar insertar uno por uno si falla el batch
            nuevos_registros = 0
            for usuario in usuarios_a_insertar:
                try:
                    db.session.add(usuario)
                    db.session.commit()
                    nuevos_registros += 1
                except IntegrityError:
                    db.session.rollback()
                    continue
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error de BD al insertar usuarios: {e}")
            raise

    return nuevos_registros


def procesar_entidades(endpoint, insertar_funcion, progress_callback=None):
    """Procesa entidades desde la API con manejo de errores mejorado.
    
    Args:
        endpoint: Nombre del endpoint de la API
        insertar_funcion: Función para insertar registros
        progress_callback: Función callback(tipo, mensaje, porcentaje) para reportar progreso
    """
    page = get_last_page(endpoint)
    nuevos_registros_totales = 0
    max_pages = 1000  # Límite de seguridad
    total_paginas_procesadas = 0
    
    if progress_callback:
        progress_callback("info", f"Iniciando procesamiento de {endpoint}...", 0)
    
    while page <= max_pages:
        url = f"https://soporte.nobissalud.com/api/v1/{endpoint}?page={page}&per_page={PER_PAGE}"
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }

        try:
            if progress_callback:
                progress_callback("progress", f"Obteniendo página {page} de {endpoint}...", int((page / max_pages) * 50))
            
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()

            registros_en_pagina = data.get("data", []) if isinstance(data, dict) else data

            if not registros_en_pagina:
                logger.info(f"No hay más registros para procesar en {endpoint}")
                if progress_callback:
                    progress_callback("info", f"No hay más registros en {endpoint}", 100)
                break

            try:
                nuevos_registros = insertar_funcion(registros_en_pagina)
                nuevos_registros_totales += nuevos_registros
                total_paginas_procesadas += 1
                
                logger.info(f"Página {page} de {endpoint}: {len(registros_en_pagina)} registros procesados, {nuevos_registros} nuevos.")
                
                if progress_callback:
                    porcentaje = min(int((page / max_pages) * 80) + 10, 95)
                    progress_callback("success", 
                        f"Página {page}: {len(registros_en_pagina)} procesados, {nuevos_registros} nuevos. Total acumulado: {nuevos_registros_totales}", 
                        porcentaje)

                if len(registros_en_pagina) < PER_PAGE:
                    logger.info(f"Última página alcanzada para {endpoint}")
                    if progress_callback:
                        progress_callback("info", f"Última página alcanzada", 95)
                    break
                
                page += 1
                if endpoint != "tickets":
                    save_last_page(endpoint, page)
                    
            except SQLAlchemyError as e:
                logger.error(f"Error de BD al procesar página {page} de {endpoint}: {e}")
                if progress_callback:
                    progress_callback("error", f"Error de BD en página {page}: {str(e)}", int((page / max_pages) * 80))
                # Continuar con la siguiente página en lugar de romper todo
                page += 1
                continue

        except Timeout as e:
            logger.error(f"Timeout al obtener página {page} de {endpoint}: {e}")
            if progress_callback:
                progress_callback("error", f"Timeout al obtener página {page}", 0)
            break
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                logger.info(f"Página {page} no encontrada para {endpoint}")
                if progress_callback:
                    progress_callback("info", f"Página {page} no encontrada (fin del proceso)", 100)
                break
            logger.error(f"Error HTTP al obtener página {page} de {endpoint}: {e}")
            if progress_callback:
                progress_callback("error", f"Error HTTP {response.status_code} en página {page}", 0)
            break
        except RequestException as e:
            logger.error(f"Error de conexión al obtener página {page} de {endpoint}: {e}")
            if progress_callback:
                progress_callback("error", f"Error de conexión: {str(e)}", 0)
            break
        except Exception as e:
            logger.error(f"Error inesperado al procesar página {page} de {endpoint}: {e}", exc_info=True)
            if progress_callback:
                progress_callback("error", f"Error inesperado: {str(e)}", 0)
            break

    if progress_callback:
        progress_callback("complete", f"Proceso completado: {nuevos_registros_totales} nuevos registros en {total_paginas_procesadas} páginas", 100)
    
    return nuevos_registros_totales

@app.route('/grabar-gestiones')
def datos_nuevos():
    """Endpoint para grabar nuevas gestiones y usuarios desde la API.
    Redirige a la página de progreso para ver el proceso en tiempo real.
    """
    return redirect(url_for('progreso_grabar_gestiones'))


@app.route('/progreso-grabar-gestiones')
def progreso_grabar_gestiones():
    """Página HTML para mostrar el progreso de grabación de gestiones."""
    return render_template('progreso_grabar.html', titulo="Grabación de Gestiones")


@app.route('/stream-grabar-gestiones')
def stream_grabar_gestiones():
    """Endpoint SSE para streaming del progreso de grabación de gestiones."""
    def generate():
        eventos_usuarios = []
        eventos_gestiones = []
        
        def usuarios_callback(tipo, mensaje, porcentaje):
            eventos_usuarios.append({
                "tipo": tipo,
                "mensaje": f"[Usuarios] {mensaje}",
                "porcentaje": min(10 + int(porcentaje * 0.4), 50)
            })
        
        def gestiones_callback(tipo, mensaje, porcentaje):
            eventos_gestiones.append({
                "tipo": tipo,
                "mensaje": f"[Gestiones] {mensaje}",
                "porcentaje": min(50 + int(porcentaje * 0.4), 90)
            })
        
        try:
            with app.app_context():
                # Enviar evento inicial
                yield f"data: {json.dumps({'tipo': 'start', 'mensaje': 'Iniciando proceso de grabación...', 'porcentaje': 0})}\n\n"
                
                # Procesar usuarios
                yield f"data: {json.dumps({'tipo': 'info', 'mensaje': 'Procesando usuarios...', 'porcentaje': 10})}\n\n"
                usuarios_nuevos = procesar_entidades("users", insertar_usuarios, progress_callback=usuarios_callback)
                
                # Emitir eventos acumulados de usuarios
                for evento in eventos_usuarios:
                    yield f"data: {json.dumps(evento)}\n\n"
                
                yield f"data: {json.dumps({'tipo': 'success', 'mensaje': f'Usuarios completados: {usuarios_nuevos} nuevos', 'porcentaje': 50})}\n\n"
                
                # Procesar gestiones
                yield f"data: {json.dumps({'tipo': 'info', 'mensaje': 'Procesando gestiones...', 'porcentaje': 50})}\n\n"
                gestiones_nuevas = procesar_entidades("tickets", insertar_gestiones, progress_callback=gestiones_callback)
                
                # Emitir eventos acumulados de gestiones
                for evento in eventos_gestiones:
                    yield f"data: {json.dumps(evento)}\n\n"
                
                yield f"data: {json.dumps({'tipo': 'success', 'mensaje': f'Gestiones completadas: {gestiones_nuevas} nuevas', 'porcentaje': 90})}\n\n"
                
                # Guardar log
                try:
                    log_entry = ExecutionLog(
                        fecha_ejecucion=datetime.now(timezone.utc),
                        nuevos_usuarios=usuarios_nuevos,
                        nuevas_gestiones=gestiones_nuevas
                    )
                    db.session.add(log_entry)
                    db.session.commit()
                    yield f"data: {json.dumps({'tipo': 'success', 'mensaje': 'Log de ejecución guardado', 'porcentaje': 95})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'tipo': 'warning', 'mensaje': f'Error al guardar log: {str(e)}', 'porcentaje': 95})}\n\n"
                
                # Enviar evento final
                resultado = {
                    "usuarios_nuevos": usuarios_nuevos,
                    "gestiones_nuevas": gestiones_nuevas
                }
                yield f"data: {json.dumps({'tipo': 'end', 'mensaje': 'Proceso completado exitosamente', 'resultado': resultado, 'porcentaje': 100})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'tipo': 'error', 'mensaje': f'Error: {str(e)}', 'porcentaje': 0})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })


@app.route('/')
def home():
        return("OK!.")

if __name__ == '__main__':
    app.run(host="0.0.0.0")