from aiogram.fsm.state import StatesGroup, State

class CadastroUsuario(StatesGroup):
    nome = State()
    email = State()
    telefone = State()
