#!/usr/bin/env python3
"""
Aplica config de deploy (Railway/Postgres/WhiteNoise) de forma idempotente.
NAO toca em pagamento, webhook, provider, models ou migrations.
Cria backup antes de gravar. So altera se o trecho existir e ainda nao foi aplicado.
"""
import re
import shutil
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SETTINGS = BASE / "config" / "settings.py"
REQS = BASE / "requirements.txt"
BACKUPS = BASE / "backups"
BACKUPS.mkdir(exist_ok=True)

NOW = datetime.now().strftime("%Y%m%d_%H%M%S")
mudancas = []
avisos = []


def backup(path: Path):
    dest = BACKUPS / f"{path.name}.bak_predeploy_{NOW}"
    shutil.copy2(path, dest)
    return dest


# ---------- DIFF 1: requirements.txt ----------
reqs = REQS.read_text(encoding="utf-8")
reqs_orig = reqs
novos = {
    "gunicorn": "gunicorn>=23.0,<24.0",
    "dj-database-url": "dj-database-url>=2.2,<3.0",
    "whitenoise": "whitenoise>=6.7,<7.0",
}
linhas_add = []
for nome, linha in novos.items():
    # ja presente? (procura o nome do pacote no inicio de alguma linha)
    if re.search(rf"(?mi)^\s*{re.escape(nome)}\b", reqs):
        avisos.append(f"requirements: '{nome}' ja presente, pulando")
    else:
        linhas_add.append(linha)
if linhas_add:
    if not reqs.endswith("\n"):
        reqs += "\n"
    reqs += "\n".join(linhas_add) + "\n"
    if reqs != reqs_orig:
        backup(REQS)
        REQS.write_text(reqs, encoding="utf-8")
        mudancas.append(f"requirements.txt: +{len(linhas_add)} pacote(s): {', '.join(linhas_add)}")

# ---------- settings.py ----------
src = SETTINGS.read_text(encoding="utf-8")
src_orig = src

# DIFF 2: import dj_database_url
if "import dj_database_url" in src:
    avisos.append("settings: 'import dj_database_url' ja presente, pulando")
else:
    anchor = "from django.core.exceptions import ImproperlyConfigured"
    if anchor in src:
        src = src.replace(anchor, anchor + "\nimport dj_database_url", 1)
        mudancas.append("settings.py: adicionado 'import dj_database_url'")
    else:
        avisos.append("settings: ancora de import nao encontrada (REVISAR MANUALMENTE)")

# DIFF 3: DATABASES com DATABASE_URL antes do POSTGRES_DB
if "dj_database_url.config" in src:
    avisos.append("settings: bloco DATABASE_URL ja presente, pulando")
else:
    alvo = 'if os.getenv("POSTGRES_DB"):'
    if alvo in src:
        novo = (
            'if os.getenv("DATABASE_URL"):\n'
            '    DATABASES = {\n'
            '        "default": dj_database_url.config(\n'
            '            conn_max_age=60,\n'
            '            ssl_require=True,\n'
            '        )\n'
            '    }\n'
            'elif os.getenv("POSTGRES_DB"):'
        )
        src = src.replace(alvo, novo, 1)
        mudancas.append("settings.py: DATABASES agora le DATABASE_URL (Railway) antes de POSTGRES_DB")
    else:
        avisos.append("settings: ancora DATABASES nao encontrada (REVISAR MANUALMENTE)")

# DIFF 4: WhiteNoise no MIDDLEWARE
if "whitenoise.middleware.WhiteNoiseMiddleware" in src:
    avisos.append("settings: WhiteNoise ja no MIDDLEWARE, pulando")
else:
    alvo_mw = '    "django.middleware.security.SecurityMiddleware",'
    if alvo_mw in src:
        src = src.replace(
            alvo_mw,
            alvo_mw + '\n    "whitenoise.middleware.WhiteNoiseMiddleware",',
            1,
        )
        mudancas.append("settings.py: WhiteNoiseMiddleware adicionado apos SecurityMiddleware")
    else:
        avisos.append("settings: ancora MIDDLEWARE nao encontrada (REVISAR MANUALMENTE)")

# DIFF 4b: STORAGES (compressao de estaticos no WhiteNoise)
if "STORAGES" in src or "STATICFILES_STORAGE" in src:
    avisos.append("settings: STORAGES/STATICFILES_STORAGE ja presente, pulando")
else:
    alvo_static = 'STATICFILES_DIRS = [BASE_DIR / "static"]'
    if alvo_static in src:
        bloco = (
            alvo_static
            + "\n\nSTORAGES = {\n"
            '    "default": {\n'
            '        "BACKEND": "django.core.files.storage.FileSystemStorage",\n'
            "    },\n"
            '    "staticfiles": {\n'
            '        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",\n'
            "    },\n"
            "}"
        )
        src = src.replace(alvo_static, bloco, 1)
        mudancas.append("settings.py: STORAGES com WhiteNoise CompressedManifest adicionado")
    else:
        avisos.append("settings: ancora STATICFILES_DIRS nao encontrada (REVISAR MANUALMENTE)")

# grava settings se mudou
if src != src_orig:
    backup(SETTINGS)
    SETTINGS.write_text(src, encoding="utf-8")

# ---------- relatorio ----------
print("=" * 60)
print(f"Timestamp backup: {NOW}")
print("=" * 60)
print("\nMUDANCAS APLICADAS:")
if mudancas:
    for m in mudancas:
        print(f"  [OK] {m}")
else:
    print("  (nenhuma — tudo ja estava aplicado)")
print("\nAVISOS / PULADOS:")
if avisos:
    for a in avisos:
        print(f"  [--] {a}")
else:
    print("  (nenhum)")
print("\nBackups em: backups/  (sufixo _predeploy_%s)" % NOW)
print("=" * 60)
