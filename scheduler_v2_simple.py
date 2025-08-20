import threading
import time

class SimpleScheduler:
    """Executor mínimo com interface compatível.
    NOTA: Implementação 'no-op' para manter o bot vivo no Railway.
    """
    def __init__(self):
        self._running = False
        self._thread = None
        self._jobs = {}

    def set_bot_instance(self, bot_instance):
        self._bot = bot_instance

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            # ganchos chamados no código original
            try:
                self._processar_fila_mensagens()
            except Exception:
                pass
            time.sleep(1)

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running

    # API superficial de jobs
    def add_job(self, job_id: str, func, *args, **kwargs):
        self._jobs[job_id] = (func, args, kwargs)

    def remove_job(self, job_id: str):
        self._jobs.pop(job_id, None)

    def get_job(self, job_id: str):
        return self._jobs.get(job_id)

    # Métodos referenciados diretamente no código
    def cancelar_mensagens_cliente_renovado(self, cliente_id: int):
        pass

    def _enviar_mensagem_fila(self, *args, **kwargs):
        pass

    def _enviar_alerta_admin(self, *args, **kwargs):
        pass

    def _processar_fila_mensagens(self, *args, **kwargs):
        pass
