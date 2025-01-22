import os
from flask import Flask, request, jsonify, render_template_string, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
from flask_migrate import Migrate
import requests

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = (
    """mssql+pyodbc://sa:SisteNob%2B25@172.16.1.200/encuestador?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"""
)# Configuracion SQL Server
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = 'smtp-mail.outlook.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'soporte@nobis.com.ar'
app.config['MAIL_PASSWORD'] = 'Noj47222'

db = SQLAlchemy(app)
mail = Mail(app)
migrate = Migrate(app, db)

# Configuración
PER_PAGE = 100
TOKEN = "uqdXYUb4k6AmcFtDOfzoPpdSTykiXPhxLe8UEpiyXtUJHw3ipa4klPhjmpwemgaT"
LAST_PAGE_FILES = {
    "tickets": "paginas/last_page_tickets.txt",
    "users": "paginas/last_page_users.txt"
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
    primera = db.Column(db.Integer, nullable=False)
    segunda = db.Column(db.Integer, nullable=False)
    tercera = db.Column(db.Integer, nullable=False)
    cuarta = db.Column(db.Integer, nullable=True)
    comentarios = db.Column(db.Text, nullable=True)
    cliente = db.Column(db.String(100), nullable=False)
    promedio_respuestas = db.Column(db.String(10), nullable=False)
    porcentaje_respuestas = db.Column(db.Float, nullable=False)
    fecha_respuesta = db.Column(db.DateTime, nullable=False)

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


def enviar_encuesta(gestion):
    with app.app_context():
        try:

            # Obtener el usuario relacionado con la gestión
            usuario = db.session.get(Usuario, gestion.created_by_id)  # Posible cambio a cliente actualizado.
            
            if not usuario:
                print(f"No se encontró un usuario con id {gestion.created_by_id}")
                return

            # Renderizar el template con contenido dinámico
            cuerpo_mensaje = render_template(
                'index.html',  # Nombre del archivo del template
                gestion_id=gestion.id,
                gestion_numero=gestion.number,
                gestion_title=gestion.title
            )

            # Configurar y enviar el mensaje
            msg = Message(
                'Encuesta de Satisfacción',
                sender=app.config['MAIL_USERNAME'],
                recipients=[usuario.email],
                html=cuerpo_mensaje  # Usar el contenido HTML renderizado
            )

            mail.send(msg)

            print(f"Encuesta enviada a {usuario.email}")
            gestion.estado_enviado = True
            return True
        except Exception as e:
            print(f"Error al enviar encuesta: {e}")
            return False


def verificar_y_enviar_encuestas():
    with app.app_context():
        try:
            ahora = datetime.now(timezone.utc)
            limite = ahora - timedelta(hours=24)
            gestiones_pendientes = Gestion.query.filter_by(estado_enviado=False).all()
            print(f"Gestiones pendientes encontradas: {len(gestiones_pendientes)}")

            for gestion in gestiones_pendientes:
                enviar_encuesta(gestion)

            # Guardar los cambios en la base de datos
            db.session.commit()
            #print("Estado de gestiones actualizado correctamente.")
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        

@app.route('/procesar-encuesta', methods=['POST'])
def procesar_encuesta():
    try:
        datos = request.form
        print("Datos recibidos:", datos)  # Esto imprimirá los datos recibidos en la consola

        # Verifica si los datos están presentes antes de convertirlos
        gestion_id = datos.get('gestion_id')
        if not gestion_id:
            raise ValueError("gestion_id no recibido")

        # Verifica si ya existe una respuesta para el gestion_id
        respuesta_existente = Respuesta.query.filter_by(gestion_id=int(gestion_id)).first()
        if respuesta_existente:
            return jsonify({
                "status": "error",
                "message": f"Ya existe una respuesta para el ticket {gestion_id}."
            }), 400

        nivel_g = datos.get('nivel')

        # Obtén las respuestas individuales, asegurándonos de no tener valores por defecto si la respuesta no existe
        respuestas = [
            int(datos.get('primera', None)) if datos.get('primera') is not None else None,
            int(datos.get('segunda', None)) if datos.get('segunda') is not None else None,
            int(datos.get('tercera', None)) if datos.get('tercera') is not None else None,
            int(datos.get('cuarta', None)) if datos.get('cuarta') is not None else None
        ]

        # Filtra las respuestas que son válidas (no None)
        respuestas_validas = [respuesta for respuesta in respuestas if respuesta is not None]

        # Si no hay respuestas válidas, no podemos calcular el promedio
        if not respuestas_validas:
            raise ValueError("No hay respuestas válidas para calcular el promedio")

        # Calcula el puntaje total
        puntaje_total = sum(respuestas_validas)

        # Calcula el puntaje máximo posible (3 puntos por respuesta)
        puntaje_maximo = len(respuestas_validas) * 3

        # Calcula el promedio de las respuestas
        promedio_respuestas = f"{puntaje_total}/{puntaje_maximo}"

        # Calcula el porcentaje de puntajes
        porcentaje = (puntaje_total / puntaje_maximo) * 100

        # Crea la nueva respuesta en la base de datos
        nueva_respuesta = Respuesta(
            gestion_id=int(gestion_id),
            nivel=nivel_g,
            primera=respuestas[0] if len(respuestas) > 0 else None,
            segunda=respuestas[1] if len(respuestas) > 1 else None,
            tercera=respuestas[2] if len(respuestas) > 2 else None,
            cuarta=respuestas[3] if len(respuestas) > 3 else None,
            comentarios=datos.get('comentarios'),
            cliente=datos.get('cliente'),
            promedio_respuestas=promedio_respuestas,
            porcentaje_respuestas=porcentaje,
            fecha_respuesta=datetime.now(timezone.utc)
        )

        db.session.add(nueva_respuesta)
        db.session.commit()

        # Redirigir al template gracias.html
        return redirect(url_for('gracias'))

    except Exception as e:
        print("Error:", e)  # Esto imprimirá el error en la consola del servidor
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/gracias')
def gracias():
    return render_template('gracias.html')


@app.route('/encuesta/<int:gestion_id>')
def mostrar_encuesta(gestion_id):
    
    try:
        gestion = Gestion.query.get_or_404(gestion_id)

        # Seleccionar el HTML según el nivel
        if gestion.level == "Nivel 1":
            template_file = 'templates/nivel_uno.html'
        elif gestion.level == "Nivel 2":
            template_file = 'templates/nivel_dos.html'
        elif gestion.level == "Nivel 3":
            template_file = 'templates/nivel_tres.html'
        else:
            print(f"Nivel desconocido: {gestion.level}")
            template_file = 'templates/nivel_uno.html'
            return

        # Leer el contenido del archivo HTML
        with open(template_file, 'r', encoding='utf-8') as file:
            html_content = file.read()

        # Reemplazar los placeholders del HTML
        html_content = html_content.replace('{{gestion_id}}', str(gestion.id))
        html_content = html_content.replace('{{titulo}}', str(gestion.title))

        
        usuario_creador = gestion.created_by_id
        print("Created by ID:", usuario_creador)
        nivel = gestion.level
        print("Level:", nivel)

        html_content = html_content.replace('{{level}}', str(nivel))
        html_content = html_content.replace('{{created_by_id}}', str(usuario_creador)) # created_by_id

        created_at_date = datetime.strptime(gestion.created_at, '%Y-%m-%dT%H:%M:%S.%fZ')
        first_response_date = datetime.strptime(gestion.first_response_at, '%Y-%m-%dT%H:%M:%S.%fZ')
        close_at_date = datetime.strptime(gestion.close_at, '%Y-%m-%dT%H:%M:%S.%fZ')

        # Diferencias
        creado_a_firstresponse = first_response_date - created_at_date
        first_closed = close_at_date - first_response_date

        primer_dif = format_timedelta(creado_a_firstresponse)
        seg_dif = format_timedelta(first_closed)
        html_content = html_content.replace('{{primer_dif}}', str(primer_dif))
        html_content = html_content.replace('{{seg_dif}}', str(seg_dif))

        return render_template_string(html_content, gestion_id=gestion_id)
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/verificar-y-enviar-encuestas', methods=['GET'])
def trigger_verificar_y_enviar_encuestas():
    try:
        #print("Iniciando verificación y envío de encuestas")
        verificar_y_enviar_encuestas()
        return "Verificación y envío de encuestas realizado"
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 502


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
    gestiones = Gestion.query.all()
    return jsonify([{
        'id': g.id,
        'encuesta_enviada': g.estado_enviado
    } for g in gestiones])


# Insertar Usuarios y gestiones
def get_last_page(endpoint, default=1):
    last_page_file = LAST_PAGE_FILES.get(endpoint)
    if last_page_file and os.path.exists(last_page_file):
        with open(last_page_file, "r") as file:
            return int(file.read().strip())
    return default

def save_last_page(endpoint, page):
    last_page_file = LAST_PAGE_FILES.get(endpoint)
    if last_page_file:
        with open(last_page_file, "w") as file:
            file.write(str(page))

def insertar_gestiones(registros):
    nuevos_registros = 0
    for gestion in registros:
        if not db.session.query(Gestion).filter_by(id=gestion.get("id")).first():
            nueva_gestion = Gestion(
                id=gestion.get("id"),
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
            created_at_date = datetime.strptime(nueva_gestion.created_at, '%Y-%m-%dT%H:%M:%S.%fZ')
            # Comparar con la fecha deseada
            if nueva_gestion.state_id == 4 and nueva_gestion.group_id == 13 and created_at_date >= datetime(2025, 1, 1): # 01/01/2025
                db.session.add(nueva_gestion)
                nuevos_registros += 1
    db.session.commit()
    return nuevos_registros


def insertar_usuarios(registros):
    nuevos_registros = 0
    for usuario in registros:
        # Validar longitud de los campos
        login = usuario.get("login")
        firstname = usuario.get("firstname")
        email = usuario.get("email")

        if any(len(campo or "") > 100 for campo in [login, firstname, email]):
            # Omitir el registro si algún campo supera los 100 caracteres
            continue

        # Verificar si el usuario ya existe
        if not db.session.query(Usuario).filter_by(id=usuario.get("id")).first():
            # Crear un nuevo usuario
            nuevo_usuario = Usuario(
                id=usuario.get("id"),
                organization_id=usuario.get("organization_id"),
                login=login,
                firstname=firstname,
                email=email,
            )
            db.session.add(nuevo_usuario)
            nuevos_registros += 1
    
    # Confirmar los cambios
    db.session.commit()
    return nuevos_registros


def procesar_entidades(endpoint, insertar_funcion):
    page = get_last_page(endpoint)
    nuevos_registros_totales = 0
    while True:
        url = f"https://soporte.nobissalud.com/api/v1/{endpoint}?page={page}&per_page={PER_PAGE}"
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            registros_en_pagina = data.get("data", []) if isinstance(data, dict) else data

            if registros_en_pagina:
                nuevos_registros = insertar_funcion(registros_en_pagina)
                nuevos_registros_totales += nuevos_registros
                print(f"Página {page}: {len(registros_en_pagina)} registros procesados, {nuevos_registros} nuevos.")

                if len(registros_en_pagina) < PER_PAGE:
                    print("Última página alcanzada.")
                    break

                page += 1
                save_last_page(endpoint, page)
            else:
                print("No hay más registros para procesar.")
                break

        except requests.exceptions.RequestException as e:
            print(f"Error al realizar la solicitud: {e}")
            break

    return nuevos_registros_totales

@app.route('/grabar-gestiones')
def datos_nuevos():
    with app.app_context():  # Asegura el contexto de la aplicación
        try:

            # Procesar usuarios
            usuarios_nuevos = procesar_entidades("users", insertar_usuarios)
            # Procesar gestiones
            gestiones_nuevas = procesar_entidades("tickets", insertar_gestiones)

            log_entry = ExecutionLog(
                fecha_ejecucion=datetime.now(),
                nuevos_usuarios=usuarios_nuevos,
                nuevas_gestiones=gestiones_nuevas
            )
            db.session.add(log_entry)
            db.session.commit()
            return jsonify("Log de ejecución registrado con éxito.")

        except Exception as e:
            print(f"Error: {e}")
            return jsonify(f"Error: {e}")


@app.route('/')
def home():
        return("OK!.")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Base de datos creada en:", os.path.join(basedir, 'encuestas.db'))

    #scheduler = BackgroundScheduler()
    #scheduler.add_job(func=datos_nuevos, trigger="interval", minutes=60)
    #scheduler.add_job(func=verificar_y_enviar_encuestas, trigger="interval", hours=2)
    #scheduler.start()

    app.run(host="0.0.0.0")