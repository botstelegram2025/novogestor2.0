from aiogram.fsm.context import FSMContext
from states import CadastroUsuario
from db import buscar_usuario, inserir_usuario

@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    user = buscar_usuario(m.from_user.id)
    if user:
        await m.answer(f"👋 Olá {user['nome']}! Você já está cadastrado.")
    else:
        await m.answer("👋 Bem-vindo! Vamos fazer seu cadastro.\nQual é o seu <b>nome</b>?")
        await state.set_state(CadastroUsuario.nome)

# 1ª etapa — Nome
@dp.message(CadastroUsuario.nome)
async def cadastro_nome(m: Message, state: FSMContext):
    await state.update_data(nome=m.text)
    await m.answer("📧 Agora me diga seu <b>email</b>:")
    await state.set_state(CadastroUsuario.email)

# 2ª etapa — Email
@dp.message(CadastroUsuario.email)
async def cadastro_email(m: Message, state: FSMContext):
    await state.update_data(email=m.text)
    await m.answer("📱 Por fim, informe seu <b>telefone</b> (com DDD):")
    await state.set_state(CadastroUsuario.telefone)

# 3ª etapa — Telefone
@dp.message(CadastroUsuario.telefone)
async def cadastro_telefone(m: Message, state: FSMContext):
    data = await state.update_data(telefone=m.text)
    inserir_usuario(
        tg_id=m.from_user.id,
        nome=data["nome"],
        email=data["email"],
        telefone=data["telefone"]
    )
    await m.answer("✅ Cadastro concluído! Agora você pode usar os comandos do bot.")
    await state.clear()
