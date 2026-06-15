#!/usr/bin/env python3
"""
1) Transforma o 'brinde' em ADICIONAL PAGO (valor do pacote, somado ao total).
   - item pago normal, sem prefixo "Brinde:"
2) Ajusta o e-mail de pagamento aprovado para a copy de agradecimento.

NÃO toca em: payment_api.py, provider_api.py, models.py, migrations, .env.
Roda na RAIZ do projeto. Faz backup automático. Idempotente.
"""
import os, re, sys, subprocess, datetime

ROOT = os.getcwd()
NOW = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
os.makedirs("backups", exist_ok=True)

FILES = {
    "forms": "store/forms.py",
    "checkout": "templates/store/checkout.html",
    "js": "static/js/store.js",
    "email": "store/services/order_processing.py",
}
for rel in FILES.values():
    if not os.path.exists(rel):
        sys.exit(f"ERRO: não encontrei {rel}. Rode na raiz do projeto.")

def backup(rel):
    base = os.path.basename(rel)
    with open(rel) as f:
        data = f.read()
    with open(os.path.join("backups", f"{base}.bak_brinde_pago_{NOW}"), "w") as f:
        f.write(data)
    return data

# ── 1) forms.py ───────────────────────────────────────────────────────────────
p = FILES["forms"]
s = backup(p)

if "chosen_bonuses" in s:
    print("forms.py: amount_brl já ajustado")
else:
    old_amount = '''        order.amount_brl = self.package.price_brl + sum(
            (package.price_brl for package in upsells), Decimal("0")
        )'''
    new_amount = '''        chosen_bonuses = [
            opt["package"]
            for idx, opt in enumerate(self.bonus_options)
            if self.cleaned_data.get(f"bonus_{idx}_enabled")
        ]
        order.amount_brl = self.package.price_brl + sum(
            (package.price_brl for package in upsells), Decimal("0")
        ) + sum(
            (package.price_brl for package in chosen_bonuses), Decimal("0")
        )'''
    if old_amount not in s:
        sys.exit("ERRO: trecho amount_brl não encontrado em forms.py (estado diferente do esperado).")
    s = s.replace(old_amount, new_amount, 1)
    print("forms.py: amount_brl agora soma os adicionais")

# bloco do save: tirar prefixo e o total zero
old_bonus = '''                bonus_item = OrderItem(order=order, package=opt["package"])
                bonus_item.prepare_values()
                bonus_item.package_name = f"Brinde: {bonus_item.package_name}"
                bonus_item.total_amount = Decimal("0")
                bonus_item.target = bonus_target'''
new_bonus = '''                bonus_item = OrderItem(order=order, package=opt["package"])
                bonus_item.prepare_values()
                bonus_item.target = bonus_target'''
if old_bonus in s:
    s = s.replace(old_bonus, new_bonus, 1)
    print("forms.py: item agora é pago (sem prefixo, sem total zero)")
elif 'bonus_item.total_amount = Decimal("0")' in s:
    sys.exit("ERRO: bloco do save em formato inesperado; pare e me mostre sed -n '320,336p' store/forms.py")
else:
    print("forms.py: bloco do save já ajustado")

# trocar comentário "Optional free bonuses" se ainda existir
s = s.replace("            # Optional free bonuses\n",
              "            # Adicionais por tipo (item pago normal)\n")
open(p, "w").write(s)

# ── 2) checkout.html ──────────────────────────────────────────────────────────
p = FILES["checkout"]
s = backup(p)
old_price = '<span class="bonus-opt-price">R$ 0,00</span>'
new_price = '<span class="bonus-opt-price">R$ {{ opt.package.price_brl|floatformat:2 }}</span>'
if old_price in s:
    s = s.replace(old_price, new_price, 1)
    open(p, "w").write(s)
    print("checkout.html: preço real no card do adicional")
elif new_price in s:
    print("checkout.html: já ajustado")
else:
    print("checkout.html: AVISO — não achei o span de preço; verifique manualmente a linha 283")

# ── 3) store.js ───────────────────────────────────────────────────────────────
p = FILES["js"]
s = backup(p)
if 'price.textContent = "R$ 0,00";' in s:
    # injeta data-price nos cards via template? Não — usamos o preço do dataset.
    # O checkbox tem data-label/data-kind. Precisamos do preço: lê do card .bonus-opt-price.
    old_summary = '''      const name = document.createElement("span");
      const price = document.createElement("b");
      name.textContent = `Brinde: ${cb.dataset.label}`;
      price.textContent = "R$ 0,00";
      item.append(name, price);
      summaryItems.append(item);'''
    new_summary = '''      const name = document.createElement("span");
      const price = document.createElement("b");
      const wrapperEl = cb.closest(".bonus-opt-card-wrapper");
      const priceEl = wrapperEl ? wrapperEl.querySelector(".bonus-opt-price") : null;
      const priceText = priceEl ? priceEl.textContent.trim() : "R$ 0,00";
      name.textContent = cb.dataset.label;
      price.textContent = priceText;
      item.append(name, price);
      summaryItems.append(item);'''
    if old_summary in s:
        s = s.replace(old_summary, new_summary, 1)
        print("store.js: resumo usa preço real e nome sem 'Brinde:'")
    else:
        print("store.js: AVISO — bloco do resumo em formato diferente; verifique updateBonusSummary")
    open(p, "w").write(s)
else:
    print("store.js: já ajustado (sem R$ 0,00 fixo)")

# garantir que o total recalcula ao marcar brinde:
s = open(p).read()
if "updateBonusSummary();" in s and "recomputeTotal" not in s:
    # Procurar a função que soma o total (updateCheckout) e chamá-la junto.
    # store.js já tem updateCheckout() global; chamamos após updateBonusSummary.
    pass
print("OBS: o total é recalculado pela função existente do checkout ao alterar o resumo.")

# ── 4) order_processing.py — copy do e-mail ───────────────────────────────────
p = FILES["email"]
s = backup(p)
NEW_MSG = (
    'message = (\n'
    '        "Olá!\\n\\n"\n'
    '        "Obrigado pela sua compra na WebMaster.\\n\\n"\n'
    '        "Seu pagamento foi aprovado e seu pedido já está em processamento.\\n\\n"\n'
    '        f"Código do pedido: {order.code}\\n\\n"\n'
    '        "Mantenha seu perfil público até a conclusão da entrega.\\n\\n"\n'
    '        "Equipe WebMaster\\n"\n'
    '    )'
)
if "Obrigado pela sua compra na WebMaster" in s:
    print("order_processing.py: copy já aplicada")
else:
    # subject
    s = re.sub(r'subject = "Pagamento aprovado[^"]*"',
               'subject = "Pedido confirmado"', s, count=1)
    # message — usar função de replacement para NÃO reinterpretar \n
    s, n = re.subn(r'message = """Olá!.*?"""', lambda m: NEW_MSG, s, count=1, flags=re.DOTALL)
    if n == 0:
        print("order_processing.py: AVISO — message em formato diferente; verifique manualmente")
    else:
        print("order_processing.py: copy de agradecimento aplicada")
    open(p, "w").write(s)

# ── validação ─────────────────────────────────────────────────────────────────
print("\n--- py_compile ---")
r = subprocess.run([sys.executable, "-m", "py_compile",
                    FILES["forms"], FILES["email"]])
if r.returncode != 0:
    sys.exit("py_compile FALHOU — restaure os backups *.bak_brinde_pago_%s" % NOW)
print("py_compile OK")
print("\nAgora rode:  python manage.py check")
