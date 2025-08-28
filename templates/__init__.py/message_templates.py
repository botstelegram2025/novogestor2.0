import re
from datetime import datetime
from typing import Dict, Any

def format_reminder_message(template: str, **kwargs) -> str:
    """
    Format reminder message template with client data
    """
    try:
        # Format currency values
        if 'plan_price' in kwargs and kwargs['plan_price'] is not None:
            kwargs['plan_price'] = f"{float(kwargs['plan_price']):.2f}".replace('.', ',')
        
        # Ensure all required fields have default values
        defaults = {
            'client_name': 'Cliente',
            'plan_name': 'Plano',
            'plan_price': '0,00',
            'due_date': datetime.now().strftime('%d/%m/%Y')
        }
        
        # Merge with defaults
        for key, default_value in defaults.items():
            if key not in kwargs or kwargs[key] is None:
                kwargs[key] = default_value
        
        return template.format(**kwargs)
        
    except KeyError as e:
        # If template has variables not provided, try to replace with default
        missing_var = str(e).strip("'")
        kwargs[missing_var] = f"[{missing_var}]"
        return template.format(**kwargs)
    except Exception as e:
        # If formatting fails, return template as-is
        return template

def format_welcome_message(template: str, client_name: str, plan_name: str = None, plan_price: float = None, due_date: str = None) -> str:
    """
    Format welcome message for new clients
    """
    return format_reminder_message(
        template,
        client_name=client_name,
        plan_name=plan_name or "Plano",
        plan_price=plan_price or 0.0,
        due_date=due_date or datetime.now().strftime('%d/%m/%Y')
    )

def format_renewal_message(template: str, client_name: str, plan_name: str = None, plan_price: float = None, due_date: str = None) -> str:
    """
    Format renewal confirmation message
    """
    return format_reminder_message(
        template,
        client_name=client_name,
        plan_name=plan_name or "Plano",
        plan_price=plan_price or 0.0,
        due_date=due_date or datetime.now().strftime('%d/%m/%Y')
    )

def get_status_emoji(status: str) -> str:
    """
    Get emoji for status display
    """
    emojis = {
        'active': '✅',
        'inactive': '❌',
        'suspended': '⏸️',
        'pending': '⏳',
        'approved': '✅',
        'rejected': '❌',
        'cancelled': '🚫',
        'sent': '✅',
        'failed': '❌'
    }
    return emojis.get(status, '❓')

def format_client_list(clients: list) -> str:
    """
    Format client list for display
    """
    if not clients:
        return "📋 Nenhum cliente cadastrado."
    
    lines = ["📋 **Seus Clientes:**\n"]
    
    for i, client in enumerate(clients, 1):
        status_emoji = get_status_emoji(client.status)
        due_date = client.due_date.strftime('%d/%m/%Y')
        price = f"R$ {client.plan_price:.2f}".replace('.', ',') if client.plan_price else "N/A"
        
        lines.append(
            f"{i}. {status_emoji} **{client.name}**\n"
            f"   📱 {client.phone_number}\n"
            f"   📦 {client.plan_name or 'Sem plano'}\n"
            f"   💰 {price}\n"
            f"   📅 Vence: {due_date}\n"
        )
    
    return "\n".join(lines)

def format_subscription_info(user) -> str:
    """
    Format subscription information for display
    """
    lines = ["💳 **Informações da Assinatura:**\n"]
    
    if user.is_trial:
        from datetime import timedelta
        trial_end_date = user.created_at.date() + timedelta(days=7)
        trial_days_left = (trial_end_date - datetime.utcnow().date()).days
        
        if trial_days_left > 0:
            lines.append(f"🆓 Período de teste: {trial_days_left} dias restantes")
            lines.append(f"📅 Expira em: {trial_end_date.strftime('%d/%m/%Y')}")
        else:
            lines.append("⚠️ Período de teste expirado")
            lines.append("💳 Assine agora para continuar usando!")
    else:
        if user.next_due_date:
            days_until_due = (user.next_due_date - datetime.utcnow()).days
            due_date = user.next_due_date.strftime('%d/%m/%Y')
            
            if days_until_due > 0:
                lines.append(f"✅ Assinatura ativa até {due_date} ({days_until_due} dias)")
            else:
                lines.append(f"⚠️ Assinatura vencida em {due_date}")
        else:
            lines.append("❌ Sem assinatura ativa")
    
    lines.append(f"\n💰 Valor mensal: R$ 20,00")
    lines.append(f"📊 Status: {'Ativo' if user.is_active else 'Inativo'}")
    
    return "\n".join(lines)

def format_payment_instructions(qr_code: str, amount: float, expires_at: str) -> str:
    """
    Format payment instructions message
    """
    amount_formatted = f"R$ {amount:.2f}".replace('.', ',')
    
    message = f"""💳 **Pagamento PIX - Assinatura Mensal**

💰 **Valor:** {amount_formatted}
⏰ **Válido até:** {expires_at}

📱 **Como pagar:**
1. Abra o app do seu banco
2. Escolha PIX → Pix Copia e Cola
3. Cole o código abaixo
4. Confirme o pagamento

📋 **CÓDIGO PIX (clique para copiar):**

```
{qr_code}
```

💡 **Dica:** Toque e segure no código acima para copiar

⚡ O pagamento é processado instantaneamente!
✅ Você receberá uma confirmação assim que for aprovado."""

    return message
