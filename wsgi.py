from app import app, datos_nuevos, verificar_y_enviar_encuestas
from apscheduler.schedulers.background import BackgroundScheduler

if __name__ == "__main__":

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=datos_nuevos, trigger="interval", minutes=60)
    scheduler.add_job(func=verificar_y_enviar_encuestas, trigger="interval", hours=2)
    scheduler.start()

    app.run()