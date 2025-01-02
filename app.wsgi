import sys
import os

# Ruta al directorio de tu aplicación
sys.path.insert(0, '/home/nobis/encuestas/flask')

# Activar el entorno virtual
activate_this = '/home/nobis/encuestas/flask/venv/bin/activate_this.py'
with open(activate_this) as file_:
    exec(file_.read(), dict(__file__=activate_this))

from app import app as application