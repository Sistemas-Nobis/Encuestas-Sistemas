"""
Tests unitarios para las funciones críticas de la aplicación.
"""
import os
import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from flask import Flask

from app import (
    format_timedelta, enviar_encuesta, insertar_gestiones, insertar_usuarios,
    get_last_page, save_last_page, procesar_encuesta, verificar_y_enviar_encuestas,
    Usuario, Gestion, Respuesta, RespuestaDetalle, db, app, AGENTES_MAP
)
from tests.conftest import test_app, client, sample_usuario, sample_gestion, sample_gestion_enviada, sample_agente


class TestFormatTimedelta:
    """Tests para la función format_timedelta."""
    
    def test_format_timedelta_mas_de_un_dia(self):
        """Test con más de un día."""
        td = timedelta(days=2, hours=3, minutes=30)
        resultado = format_timedelta(td)
        assert "2 dias" in resultado
        assert "3 horas" in resultado
        assert "30 minutos" in resultado
    
    def test_format_timedelta_un_dia(self):
        """Test con exactamente un día."""
        td = timedelta(days=1, hours=2, minutes=15)
        resultado = format_timedelta(td)
        assert "1 dia" in resultado
        assert "2 horas" in resultado
        assert "15 minutos" in resultado
    
    def test_format_timedelta_sin_dias(self):
        """Test sin días, solo horas y minutos."""
        td = timedelta(hours=5, minutes=45)
        resultado = format_timedelta(td)
        assert "dias" not in resultado
        assert "5 horas" in resultado
        assert "45 minutos" in resultado
    
    def test_format_timedelta_solo_minutos(self):
        """Test con solo minutos."""
        td = timedelta(minutes=30)
        resultado = format_timedelta(td)
        assert "0 horas" in resultado
        assert "30 minutos" in resultado


class TestEnviarEncuesta:
    """Tests para la función enviar_encuesta."""
    
    @patch('app.mail.send')
    @patch('app.render_template')
    def test_enviar_encuesta_exitoso(self, mock_render, mock_mail_send, test_app, sample_gestion, sample_usuario):
        """Test de envío exitoso de encuesta."""
        with test_app.app_context():
            mock_render.return_value = "<html>Test</html>"
            mock_mail_send.return_value = True
            
            resultado = enviar_encuesta(sample_gestion, intentos=1, retraso_reintento=0)
            
            assert resultado is True
            assert sample_gestion.estado_enviado is True
            mock_render.assert_called_once()
            mock_mail_send.assert_called_once()
    
    def test_enviar_encuesta_ya_enviada(self, test_app, sample_gestion_enviada):
        """Test cuando la gestión ya fue enviada."""
        with test_app.app_context():
            resultado = enviar_encuesta(sample_gestion_enviada, intentos=1, retraso_reintento=0)
            assert resultado is True
    
    def test_enviar_encuesta_sin_created_by_id(self, test_app):
        """Test cuando la gestión no tiene created_by_id."""
        with test_app.app_context():
            gestion = Gestion(
                id=999,
                number='TICKET-999',
                title='Test',
                estado_enviado=False,
                created_by_id=None
            )
            db.session.add(gestion)
            db.session.commit()
            
            resultado = enviar_encuesta(gestion, intentos=1, retraso_reintento=0)
            assert resultado is False
    
    def test_enviar_encuesta_usuario_no_existe(self, test_app):
        """Test cuando el usuario no existe."""
        with test_app.app_context():
            gestion = Gestion(
                id=998,
                number='TICKET-998',
                title='Test',
                estado_enviado=False,
                created_by_id=99999  # Usuario que no existe
            )
            db.session.add(gestion)
            db.session.commit()
            
            resultado = enviar_encuesta(gestion, intentos=1, retraso_reintento=0)
            assert resultado is False
    
    @patch('app.mail.send')
    @patch('app.render_template')
    def test_enviar_encuesta_error_reintento(self, mock_render, mock_mail_send, test_app, sample_gestion, sample_usuario):
        """Test de reintentos cuando falla el envío."""
        with test_app.app_context():
            mock_render.return_value = "<html>Test</html>"
            mock_mail_send.side_effect = [Exception("Error de conexión"), None]
            
            resultado = enviar_encuesta(sample_gestion, intentos=2, retraso_reintento=0)
            
            # Debería fallar después de 2 intentos
            assert resultado is False
            assert mock_mail_send.call_count == 2


class TestInsertarGestiones:
    """Tests para la función insertar_gestiones."""
    
    def test_insertar_gestiones_nueva(self, test_app, sample_usuario):
        """Test de inserción de nueva gestión válida."""
        with test_app.app_context():
            # Crear usuario updated_by
            usuario2 = Usuario(
                id=2,
                login='analista',
                firstname='Analista',
                email='analista@nobis.com.ar',
                organization_id=1
            )
            db.session.add(usuario2)
            db.session.commit()
            
            registros = [{
                "id": 100,
                "group_id": 13,
                "priority_id": 1,
                "state_id": 4,
                "number": "TICKET-100",
                "title": "Test Ticket",
                "owner_id": 1,
                "customer_id": 1,
                "first_response_at": "2025-01-15T10:00:00.000Z",
                "close_at": "2025-01-15T12:00:00.000Z",
                "updated_by_id": 2,
                "created_by_id": 1,
                "created_at": "2025-01-15T10:00:00.000Z",
                "updated_at": "2025-01-15T12:00:00.000Z",
                "type": "incident",
                "category": "test",
                "niveles": "Nivel 1"
            }]
            
            resultado = insertar_gestiones(registros)
            
            assert resultado == 1
            gestion = Gestion.query.get(100)
            assert gestion is not None
            assert gestion.number == "TICKET-100"
    
    def test_insertar_gestiones_ya_existe(self, test_app, sample_gestion):
        """Test cuando la gestión ya existe."""
        with test_app.app_context():
            registros = [{
                "id": sample_gestion.id,
                "group_id": 13,
                "state_id": 4,
                "created_at": "2025-01-15T10:00:00.000Z",
                "created_by_id": 1,
                "updated_by_id": 1,
                "niveles": "Nivel 1"
            }]
            
            resultado = insertar_gestiones(registros)
            assert resultado == 0
    
    def test_insertar_gestiones_filtro_blacklist(self, test_app):
        """Test que filtra gestiones de usuarios en blacklist."""
        with test_app.app_context():
            # Usuario en blacklist
            usuario_blacklist = Usuario(
                id=10,
                login='blacklist_user',
                firstname='Blacklist',
                email='lazaro.gonzalez@nobis.com.ar',  # En blacklist
                organization_id=1
            )
            usuario2 = Usuario(
                id=11,
                login='analista2',
                firstname='Analista',
                email='analista2@nobis.com.ar',
                organization_id=1
            )
            db.session.add_all([usuario_blacklist, usuario2])
            db.session.commit()
            
            registros = [{
                "id": 200,
                "group_id": 13,
                "state_id": 4,
                "created_at": "2025-01-15T10:00:00.000Z",
                "created_by_id": 10,  # Usuario en blacklist
                "updated_by_id": 11,
                "niveles": "Nivel 1"
            }]
            
            resultado = insertar_gestiones(registros)
            assert resultado == 0  # No debería insertar
    
    def test_insertar_gestiones_filtro_fecha(self, test_app, sample_usuario):
        """Test que filtra gestiones anteriores a 2025-01-01."""
        with test_app.app_context():
            usuario2 = Usuario(
                id=3,
                login='analista3',
                firstname='Analista',
                email='analista3@nobis.com.ar',
                organization_id=1
            )
            db.session.add(usuario2)
            db.session.commit()
            
            registros = [{
                "id": 300,
                "group_id": 13,
                "state_id": 4,
                "created_at": "2024-12-31T10:00:00.000Z",  # Antes de 2025
                "created_by_id": 1,
                "updated_by_id": 3,
                "niveles": "Nivel 1"
            }]
            
            resultado = insertar_gestiones(registros)
            assert resultado == 0  # No debería insertar


class TestInsertarUsuarios:
    """Tests para la función insertar_usuarios."""
    
    def test_insertar_usuarios_nuevo(self, test_app):
        """Test de inserción de nuevo usuario."""
        with test_app.app_context():
            registros = [{
                "id": 50,
                "login": "nuevo_usuario",
                "firstname": "Nuevo",
                "email": "nuevo@nobis.com.ar",
                "organization_id": 1
            }]
            
            resultado = insertar_usuarios(registros)
            
            assert resultado == 1
            usuario = Usuario.query.get(50)
            assert usuario is not None
            assert usuario.login == "nuevo_usuario"
    
    def test_insertar_usuarios_ya_existe(self, test_app, sample_usuario):
        """Test cuando el usuario ya existe."""
        with test_app.app_context():
            registros = [{
                "id": sample_usuario.id,
                "login": "test_user",
                "firstname": "Test",
                "email": "test@nobis.com.ar",
                "organization_id": 1
            }]
            
            resultado = insertar_usuarios(registros)
            assert resultado == 0
    
    def test_insertar_usuarios_campo_largo(self, test_app):
        """Test que omite usuarios con campos muy largos."""
        with test_app.app_context():
            registros = [{
                "id": 60,
                "login": "a" * 101,  # Más de 100 caracteres
                "firstname": "Test",
                "email": "test@nobis.com.ar",
                "organization_id": 1
            }]
            
            resultado = insertar_usuarios(registros)
            assert resultado == 0
    
    def test_insertar_usuarios_sin_email(self, test_app):
        """Test que omite usuarios sin email."""
        with test_app.app_context():
            registros = [{
                "id": 70,
                "login": "sin_email",
                "firstname": "Sin",
                "email": None,
                "organization_id": 1
            }]
            
            resultado = insertar_usuarios(registros)
            assert resultado == 0


class TestGetLastPage:
    """Tests para las funciones get_last_page y save_last_page."""
    
    def test_get_last_page_archivo_existe(self, temp_dir):
        """Test cuando el archivo existe."""
        import app as app_module
        original_files = app_module.LAST_PAGE_FILES.copy()
        
        # Crear archivo temporal
        test_file = os.path.join(temp_dir, "test_page.txt")
        os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, "w") as f:
            f.write("5")
        
        # Modificar temporalmente LAST_PAGE_FILES
        app_module.LAST_PAGE_FILES["test"] = test_file
        
        resultado = get_last_page("test", default=1)
        assert resultado == 5
        
        # Restaurar
        app_module.LAST_PAGE_FILES = original_files
    
    def test_get_last_page_archivo_no_existe(self):
        """Test cuando el archivo no existe."""
        resultado = get_last_page("endpoint_inexistente", default=1)
        assert resultado == 1
    
    def test_save_last_page(self, temp_dir):
        """Test de guardado de página."""
        import app as app_module
        original_files = app_module.LAST_PAGE_FILES.copy()
        
        test_file = os.path.join(temp_dir, "test_save.txt")
        app_module.LAST_PAGE_FILES["test_save"] = test_file
        
        save_last_page("test_save", 10)
        
        assert os.path.exists(test_file)
        with open(test_file, "r") as f:
            contenido = f.read().strip()
            assert contenido == "10"
        
        # Restaurar
        app_module.LAST_PAGE_FILES = original_files


class TestProcesarEncuesta:
    """Tests para el endpoint procesar_encuesta."""
    
    def test_procesar_encuesta_exitoso(self, client, test_app, sample_gestion, sample_agente):
        """Test de procesamiento exitoso de encuesta."""
        with test_app.app_context():
            # Asegurar que el agente existe
            if not Usuario.query.get(sample_agente.id):
                db.session.add(sample_agente)
                db.session.commit()
            
            # Actualizar gestión con owner_id del agente
            sample_gestion.owner_id = sample_agente.id
            db.session.commit()
            
            response = client.post('/procesar-encuesta', data={
                'gestion_id': sample_gestion.id,
                'nivel': 'Nivel 1',
                'cliente': 'Cliente Test',
                'primera': '3',
                'segunda': '2',
                'tercera': '3',
                'comentarios': 'Test comentario'
            }, follow_redirects=False)
            
            # Debería redirigir a gracias
            assert response.status_code in [302, 200]
            
            # Verificar que se creó la respuesta
            respuesta = Respuesta.query.filter_by(gestion_id=sample_gestion.id).first()
            assert respuesta is not None
            assert respuesta.porcentaje_respuestas > 0
    
    def test_procesar_encuesta_sin_gestion_id(self, client, test_app):
        """Test sin gestion_id."""
        with test_app.app_context():
            response = client.post('/procesar-encuesta', data={})
            
            assert response.status_code == 400
            data = response.get_json()
            assert data['status'] == 'error'
    
    def test_procesar_encuesta_gestion_no_existe(self, client, test_app):
        """Test con gestión que no existe."""
        with test_app.app_context():
            response = client.post('/procesar-encuesta', data={
                'gestion_id': 99999
            })
            
            assert response.status_code == 404
    
    def test_procesar_encuesta_ya_respondida(self, client, test_app, sample_gestion, sample_agente):
        """Test cuando ya existe una respuesta."""
        with test_app.app_context():
            sample_gestion.owner_id = sample_agente.id
            db.session.commit()
            
            # Crear respuesta existente
            respuesta = Respuesta(
                gestion_id=sample_gestion.id,
                nivel='Nivel 1',
                cliente='Test',
                promedio_respuestas='6/9',
                porcentaje_respuestas=66.67,
                fecha_respuesta=datetime.now(timezone.utc),
                agente_id=sample_agente.id,
                agente_nombre='Test'
            )
            db.session.add(respuesta)
            db.session.commit()
            
            response = client.post('/procesar-encuesta', data={
                'gestion_id': sample_gestion.id,
                'primera': '3'
            })
            
            assert response.status_code == 400
            data = response.get_json()
            assert 'Ya existe una respuesta' in data['message']
    
    def test_procesar_encuesta_sin_respuestas_validas(self, client, test_app, sample_gestion, sample_agente):
        """Test sin respuestas válidas."""
        with test_app.app_context():
            sample_gestion.owner_id = sample_agente.id
            db.session.commit()
            
            response = client.post('/procesar-encuesta', data={
                'gestion_id': sample_gestion.id,
                'nivel': 'Nivel 1',
                'cliente': 'Test'
            })
            
            assert response.status_code == 400
            data = response.get_json()
            assert 'respuestas válidas' in data['message']


class TestVerificarYEnviarEncuestas:
    """Tests para la función verificar_y_enviar_encuestas."""
    
    @patch('app.enviar_encuesta')
    def test_verificar_y_enviar_encuestas_exitoso(self, mock_enviar, test_app, sample_gestion):
        """Test de verificación y envío exitoso."""
        with test_app.app_context():
            mock_enviar.return_value = True
            
            resultado = verificar_y_enviar_encuestas()
            
            assert resultado['exitosos'] == 1
            assert resultado['fallidos'] == 0
            mock_enviar.assert_called_once()
    
    @patch('app.enviar_encuesta')
    def test_verificar_y_enviar_encuestas_con_fallos(self, mock_enviar, test_app):
        """Test con algunos fallos."""
        with test_app.app_context():
            # Crear dos gestiones
            gestion1 = Gestion(
                id=1001,
                number='TICKET-1001',
                title='Test 1',
                estado_enviado=False,
                created_by_id=1,
                created_at='2025-01-15T10:00:00.000Z'
            )
            gestion2 = Gestion(
                id=1002,
                number='TICKET-1002',
                title='Test 2',
                estado_enviado=False,
                created_by_id=1,
                created_at='2025-01-15T10:00:00.000Z'
            )
            db.session.add_all([gestion1, gestion2])
            db.session.commit()
            
            # Una exitosa, una fallida
            mock_enviar.side_effect = [True, False]
            
            resultado = verificar_y_enviar_encuestas()
            
            assert resultado['exitosos'] == 1
            assert resultado['fallidos'] == 1


class TestEndpoints:
    """Tests para endpoints principales."""
    
    def test_home_endpoint(self, client):
        """Test del endpoint home."""
        response = client.get('/')
        assert response.status_code == 200
    
    def test_gracias_endpoint(self, client, test_app):
        """Test del endpoint gracias."""
        with test_app.app_context():
            response = client.get('/gracias')
            assert response.status_code == 200
    
    def test_mostrar_encuesta(self, client, test_app, sample_gestion):
        """Test del endpoint mostrar_encuesta."""
        with test_app.app_context():
            response = client.get(f'/encuesta/{sample_gestion.id}')
            assert response.status_code == 200
    
    def test_mostrar_encuesta_no_existe(self, client, test_app):
        """Test cuando la gestión no existe."""
        with test_app.app_context():
            response = client.get('/encuesta/99999')
            assert response.status_code == 404
    
    @patch('app.verificar_y_enviar_encuestas')
    def test_trigger_verificar_y_enviar_encuestas(self, mock_verificar, client, test_app):
        """Test del endpoint trigger."""
        with test_app.app_context():
            mock_verificar.return_value = {"exitosos": 5, "fallidos": 0}
            
            response = client.get('/verificar-y-enviar-encuestas')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'success'
            assert data['resultado']['exitosos'] == 5

