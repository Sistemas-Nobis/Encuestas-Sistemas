from apscheduler.schedulers.blocking import BlockingScheduler
from app import datos_nuevos, verificar_y_enviar_encuestas

def start_scheduler():
    scheduler = BlockingScheduler()
    scheduler.add_job(func=datos_nuevos, trigger="interval", minutes=60)
    scheduler.add_job(func=verificar_y_enviar_encuestas, trigger="interval", hours=2)
    print("Iniciando el planificador...")
    scheduler.start()

if __name__ == "__main__":
    start_scheduler()