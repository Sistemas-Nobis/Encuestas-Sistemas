"""
Configuración y fixtures para pytest.
"""
import os
import pytest
import tempfile
from datetime import datetime, timezone
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail

# Importar modelos y funciones desde app
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importar después de configurar el path
from app import (
    app, db, mail, Usuario, Gestion, Respuesta, RespuestaDetalle
)


@pytest.fixture(scope='function')
def test_app():
    """Crea una aplicación Flask para testing con base de datos en memoria."""
    # Configurar base de datos en memoria SQLite para tests
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['MAIL_SUPPRESS_SEND'] = True  # No enviar emails reales en tests
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(test_app):
    """Cliente de prueba para hacer requests."""
    return test_app.test_client()


@pytest.fixture(scope='function')
def sample_usuario(test_app):
    """Crea un usuario de prueba."""
    with test_app.app_context():
        usuario = Usuario(
            id=1,
            login='test_user',
            firstname='Test',
            email='lazaro.gonzalez@nobis.com.ar',
            organization_id=1
        )
        db.session.add(usuario)
        db.session.commit()
        return usuario


@pytest.fixture(scope='function')
def sample_gestion(test_app, sample_usuario):
    """Crea una gestión de prueba."""
    with test_app.app_context():
        gestion = Gestion(
            id=1,
            number='TICKET-001',
            title='Test Ticket',
            state_id=4,
            group_id=13,
            owner_id=1,
            created_by_id=1,
            updated_by_id=1,
            created_at='2025-01-15T10:00:00.000Z',
            first_response_at='2025-01-15T11:00:00.000Z',
            close_at='2025-01-15T12:00:00.000Z',
            level='Nivel 1',
            estado_enviado=False
        )
        db.session.add(gestion)
        db.session.commit()
        return gestion


@pytest.fixture(scope='function')
def sample_gestion_enviada(test_app, sample_usuario):
    """Crea una gestión ya enviada."""
    with test_app.app_context():
        gestion = Gestion(
            id=2,
            number='TICKET-002',
            title='Test Ticket Enviado',
            state_id=4,
            group_id=13,
            owner_id=1,
            created_by_id=1,
            updated_by_id=1,
            created_at='2025-01-15T10:00:00.000Z',
            level='Nivel 1',
            estado_enviado=True
        )
        db.session.add(gestion)
        db.session.commit()
        return gestion


@pytest.fixture(scope='function')
def sample_agente(test_app):
    """Crea un agente de prueba."""
    with test_app.app_context():
        agente = Usuario(
            id=10787,
            login='juan.cuevas',
            firstname='Juan',
            email='juan.cuevas@nobis.com.ar',
            organization_id=1
        )
        db.session.add(agente)
        db.session.commit()
        return agente


@pytest.fixture(scope='function')
def temp_dir():
    """Crea un directorio temporal para archivos de prueba."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

