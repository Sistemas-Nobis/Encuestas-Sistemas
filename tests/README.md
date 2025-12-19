# Tests Unitarios

Este directorio contiene los tests unitarios para la aplicación Flask.

## Estructura

- `conftest.py`: Configuración y fixtures compartidos para pytest
- `test_app.py`: Tests para las funciones críticas de la aplicación

## Instalación

Instalar las dependencias de testing:

```bash
pip install -r requirements.txt
```

## Ejecutar Tests

Ejecutar todos los tests:

```bash
pytest
```

Ejecutar con cobertura:

```bash
pytest --cov=app --cov-report=html
```

Ejecutar un test específico:

```bash
pytest tests/test_app.py::TestFormatTimedelta::test_format_timedelta_mas_de_un_dia
```

Ejecutar tests con más verbosidad:

```bash
pytest -v
```

## Funciones Testeadas

### Funciones Utilitarias
- `format_timedelta`: Formateo de diferencias de tiempo

### Funciones de Negocio
- `enviar_encuesta`: Envío de encuestas por email
- `insertar_gestiones`: Inserción de gestiones desde API
- `insertar_usuarios`: Inserción de usuarios desde API
- `verificar_y_enviar_encuestas`: Verificación y envío masivo

### Endpoints
- `/procesar-encuesta`: Procesamiento de respuestas de encuesta
- `/encuesta/<id>`: Visualización de encuesta
- `/verificar-y-enviar-encuestas`: Trigger manual de envío
- `/gracias`: Página de agradecimiento

## Fixtures Disponibles

- `test_app`: Aplicación Flask configurada para testing
- `client`: Cliente de prueba para hacer requests
- `sample_usuario`: Usuario de prueba
- `sample_gestion`: Gestión de prueba
- `sample_gestion_enviada`: Gestión ya enviada
- `sample_agente`: Agente de prueba
- `temp_dir`: Directorio temporal para archivos

## Notas

- Los tests usan SQLite en memoria para evitar dependencias de BD externa
- Los emails están suprimidos en modo testing (`MAIL_SUPPRESS_SEND = True`)
- Se usan mocks para funciones externas (envío de emails, requests HTTP)

