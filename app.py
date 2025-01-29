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
    with app.app_context():
        for intento in range(intentos):
            try:
                # Verificar si ya fue enviada
                if gestion.estado_enviado:
                    print(f"Gestión {gestion.id} ya fue enviada. No se enviará de nuevo.")
                    return True

                # Obtener el usuario relacionado con la gestión
                usuario = db.session.get(Usuario, gestion.created_by_id)
                if not usuario:
                    print(f"No se encontró un usuario con id {gestion.created_by_id}")
                    return False

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
                    html=cuerpo_mensaje
                )

                mail.send(msg)
                print(f"Encuesta enviada a {usuario.email}")

                # Actualizar estado de la gestión
                gestion.estado_enviado = True
                db.session.commit()
                return True  # Salir del bucle al enviar exitosamente

            except Exception as e:
                print(f"Error al enviar encuesta (intento {intento + 1}/{intentos}): {e}")
                if intento < intentos - 1:
                    print(f"Reintentando en {retraso_reintento} segundos...")
                    time.sleep(retraso_reintento)
                else:
                    print(f"No se pudo enviar la encuesta para la gestión {gestion.id} después de {intentos} intentos.")
                    return False

import time
def verificar_y_enviar_encuestas():
    with app.app_context():
        try:
            ahora = datetime.now(timezone.utc)
            limite = ahora - timedelta(hours=24)
            gestiones_pendientes = Gestion.query.filter_by(estado_enviado=False).all()
            print(f"Gestiones pendientes encontradas: {len(gestiones_pendientes)}")

            count = 0
            print(gestiones_pendientes)
            for gestion in gestiones_pendientes:
                enviar_encuesta(gestion)
                time.sleep(5)
                #if gestion.created_by_id == 6770:
                #    count += 1
                #    print(f"Encuestas de sherrera: {count}")
                #    enviar_encuesta(gestion)
                #    time.sleep(5)
                #else:
                #    pass
                    #print(f"Encuestas de otros usuarios: {gestion.created_by_id}")

            # Guardar los cambios en la base de datos
            db.session.commit()
            #print("Estado de gestiones actualizado correctamente.")
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        
# Definir la zona horaria de Buenos Aires
zona_horaria = timezone(timedelta(hours=-3))

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
        comentarios = datos.get('comentarios', '')

        # Extraer respuestas del formulario
        preguntas = ["Primera", "Segunda", "Tercera", "Cuarta"]
        respuestas = {
            "Primera": int(datos.get('primera', 0)) if datos.get('primera') else None,
            "Segunda": int(datos.get('segunda', 0)) if datos.get('segunda') else None,
            "Tercera": int(datos.get('tercera', 0)) if datos.get('tercera') else None,
            "Cuarta": int(datos.get('cuarta', 0)) if datos.get('cuarta') else None
        }

        # Filtrar respuestas válidas
        respuestas_validas = {k: v for k, v in respuestas.items() if v is not None}
        if not respuestas_validas:
            raise ValueError("No hay respuestas válidas para calcular el promedio")

        # Calcular puntajes
        puntaje_total = sum(respuestas_validas.values())
        puntaje_maximo = len(respuestas_validas) * 3
        promedio_respuestas = f"{puntaje_total}/{puntaje_maximo}"
        porcentaje = (puntaje_total / puntaje_maximo) * 100

        # Obtener fecha actual en Buenos Aires
        respuesta_time = datetime.now(zona_horaria).strftime('%d-%m-%Y %H:%M:%S')

        # Obtener datos de la gestión y agente
        gestion = db.session.get(Gestion, gestion_id)
        usuario_age = db.session.get(Usuario, gestion.owner_id)

        if usuario_age.id == 10787:
            age_nombre = 'Juan Cuevas'
        elif usuario_age.id in (7211, 5922):
            age_nombre = 'Agustin Jimenez'
        elif usuario_age.id == 8506:
            age_nombre = 'Valentina Martinelli'
        elif usuario_age.id in (3733, 6859):
            age_nombre = 'Lazaro Gonzalez'
        elif usuario_age.id in (33, 6716):
            age_nombre = 'Nahuel Saracho'
        elif usuario_age.id == 12066:
            age_nombre = 'Iara Zalazar'
        else:
            age_nombre = 'Desconocido'

        # Crear la respuesta principal
        nueva_respuesta = Respuesta(
            gestion_id=int(gestion_id),
            nivel=nivel_g,
            comentarios=comentarios,
            cliente=datos.get('cliente'),
            promedio_respuestas=promedio_respuestas,
            porcentaje_respuestas=porcentaje,
            fecha_respuesta=respuesta_time,
            agente_id=usuario_age.id,
            agente_nombre=age_nombre
        )
        db.session.add(nueva_respuesta)
        db.session.commit()  # Se necesita para obtener el ID de la respuesta

        # Guardar respuestas individuales en `RespuestaDetalle`
        detalles = [
            RespuestaDetalle(respuesta_id=nueva_respuesta.id, pregunta=preg, valor=valor)
            for preg, valor in respuestas_validas.items()
        ]
        db.session.add_all(detalles)
        db.session.commit()

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
        #print("Created by ID:", usuario_creador)
        nivel = gestion.level
        #print("Level:", nivel)

        html_content = html_content.replace('{{level}}', str(nivel))
        html_content = html_content.replace('{{created_by_id}}', str(usuario_creador)) # created_by_id

        created_at_date = datetime.strptime(gestion.created_at, '%Y-%m-%dT%H:%M:%S.%fZ')
        if gestion.first_response_at is not None:
            first_response_date = datetime.strptime(gestion.first_response_at, '%Y-%m-%dT%H:%M:%S.%fZ')
        else:
            first_response_date = created_at_date
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

import re

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

            # Obtener el usuario relacionado con la gestión
            usuario = db.session.get(Usuario, nueva_gestion.created_by_id)  # Posible cambio a cliente actualizado.
            #print(usuario.email)

            validez = False

            # Verificar que el correo electrónico tenga el dominio "nobis" o "nobissalud"
            if re.search(r"@(nobis|nobissalud)\.com(\.ar)?$", usuario.email):
                #print("El correo tiene un dominio válido.")
                validez = True
                #print(validez)
            else:
                #print("El correo no tiene un dominio válido.")
                pass
            
            if not usuario:
                print(f"No se encontró un usuario con id {gestion.created_by_id}")
                return

            # Comparar con la fecha deseada
            if nueva_gestion.state_id == 4 and nueva_gestion.group_id == 13 and created_at_date >= datetime(2025, 1, 1) and validez: # 01/01/2025
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
                if endpoint != "tickets":
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
    app.run(host="0.0.0.0")