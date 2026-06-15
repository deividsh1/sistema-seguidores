# WebMaster

Loja Django em formato landing page + catálogo para pacotes digitais de
Instagram e TikTok. O cliente escolhe um pacote com preço local em BRL, confirma
o perfil, paga via Pix e acompanha o pedido sem criar conta.

## Recursos

- Home moderna com benefícios, depoimentos, FAQ e CTA.
- Páginas `/instagram/` e `/tiktok/`.
- Modelagem `Platform`, `Service`, `Package`, `Order`, `OrderItem`,
  `PaymentLog` e `ProviderLog`.
- Preços e quantidades controlados manualmente no Django Admin.
- Checkout com aceite obrigatório dos termos e confirmação de perfil público.
- Registro da versão dos termos, data do aceite, IP e user agent.
- Pedido com snapshots `amount_brl`, `provider_service_id`, status do fornecedor
  e ID externo do pagamento, preservando o histórico mesmo após mudanças no catálogo.
- Pix real via Mercado Pago, com modo simulado para desenvolvimento.
- Webhook autenticado, consulta do pagamento e conferência de ID, pedido e valor.
- Envio automático somente depois do pagamento confirmado.
- Carrinho com até três serviços complementares e preço recalculado no servidor.
- Comentários personalizados com um comentário por linha e envio somente após pagamento.
- Prévia de perfil pela rota interna `/api/profile-preview/`, com fallback seguro.
- Catálogo mobile-first com âncoras, cards escuros e pacotes em destaque.
- Notificações rotativas sem foto e sem repetir nomes durante a sessão.
- Botão de suporte configurável e página neutra para campanhas em `/servicos-digitais/`.
- Limitação de tentativas no checkout, consulta e webhook.
- Respostas externas sanitizadas antes de serem gravadas em logs.
- SQLite no desenvolvimento e PostgreSQL preparado para produção.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver
```

A loja fica em `http://127.0.0.1:8000/` e o Admin em
`http://127.0.0.1:8000/admin/`.

## Catálogo e preços

O comando `seed_demo` cria Instagram e TikTok, os serviços iniciais e cinco
pacotes por serviço. Os preços são exemplos locais e o TikTok começa mais caro.

No Admin:

- **Plataformas**: nome, descrição e visibilidade.
- **Serviços**: nome e `provider_service_id` técnico.
- **Pacotes**: quantidade, preço manual em BRL, destaque e visibilidade.

Alterar **preço em reais** no pacote muda o valor cobrado. O pedido copia
quantidade, preço e `provider_service_id` no momento da compra, evitando o erro
de ID técnico vazio ou alterações retroativas.

Os campos opcionais **quantidade mínima** e **quantidade máxima** do serviço
podem ser configurados no Admin. Pacotes fora desses limites não passam pelo
checkout. Serviços ativos sem `provider_service_id` também não podem ser comprados.

O catálogo inicial mantém somente Seguidores, Curtidas e Visualizações no
TikTok. No Instagram, também mantém Comentários Personalizados. Para desativar
serviços brasileiros antigos sem apagar pedidos históricos:

```bash
python manage.py disable_brazilian_services
```

## Carrinho e complementos

No checkout, pacotes de outros serviços da mesma plataforma aparecem como
complementos. O cliente pode selecionar até três, mas apenas um pacote por
serviço. JavaScript atualiza o resumo visual, enquanto o Django valida IDs,
preços e total novamente no servidor. Cada item é enviado separadamente após o
pagamento aprovado e possui status próprio no Admin.

Serviços marcados como **exige comentários personalizados** não aparecem como
upsell, pois precisam de texto próprio. No checkout deles, o cliente informa um
comentário por linha e a quantidade de linhas não vazias deve ser igual à
quantidade do pacote. O ID técnico continua configurado somente no serviço.

O pacote de 10.000 Curtidas Instagram é criado inativo com preço `R$ 0,00`.
Defina um preço positivo no Admin antes de ativá-lo.

## Teste completo sem cobrar

Mantenha:

```dotenv
PAYMENT_SIMULATED=True
PROVIDER_SIMULATED=True
```

Crie um pedido pela loja e aprove o Pix simulado:

```bash
python manage.py simulate_payment CODIGO_DO_PEDIDO
```

## Integração de entrega

Configure apenas no `.env`:

```dotenv
PROVIDER_API_URL=url-fornecida-pela-integracao
PROVIDER_API_KEY=chave-secreta
PROVIDER_SIMULATED=False
```

As operações `services`, `add`, `status`, `refill`, `cancel` e `balance` estão
isoladas em `store/services/provider_api.py`. Nenhuma chave, identidade da
integração ou resposta sensível é mostrada ao cliente.

## Pagamento Pix

A integração do Mercado Pago está em `store/services/payment_api.py`:

- `create_pix_charge(order)`
- `get_payment_status(external_payment_id)`
- `parse_payment_webhook(request)`

Para ativar cobranças reais, crie uma aplicação no Mercado Pago, copie as
credenciais para o `.env` e configure:

```dotenv
MERCADO_PAGO_ACCESS_TOKEN=access-token-secreto
MERCADO_PAGO_PUBLIC_KEY=public-key
MERCADO_PAGO_WEBHOOK_SECRET=assinatura-secreta-longa
MERCADO_PAGO_WEBHOOK_TOLERANCE_SECONDS=600
PAYMENT_PROVIDER=mercadopago
PAYMENT_SIMULATED=False
PUBLIC_BASE_URL=https://loja.example.com
```

Cadastre no painel do Mercado Pago o evento de pagamentos apontando para:

```text
https://loja.example.com/webhooks/mercadopago/
```

O backend cria o Pix em `/v1/payments` usando `X-Idempotency-Key`, exibe o QR
Code e o código copia e cola retornados pelo Mercado Pago e salva o ID externo.
Ao receber o webhook, valida `X-Signature`, consulta o pagamento diretamente na
API e só então aprova o pedido. Notificações repetidas não duplicam o envio.
Falhas incertas no fornecedor precisam ser reprocessadas explicitamente no
Admin, evitando reenvio automático acidental.

O botão **Já paguei, verificar status** executa a mesma conferência idempotente.
A chave pública fica preparada para futuras integrações no navegador, mas o
fluxo atual é totalmente backend e não expõe credenciais.

`PUBLIC_BASE_URL=http://127.0.0.1:8000` serve apenas para desenvolvimento. Para
receber webhooks reais, use uma URL pública HTTPS. Consulte a documentação
oficial do [Pix](https://www.mercadopago.com.br/developers/pt/docs/checkout-bricks/payment-brick/payment-submission/pix)
e de [notificações de pagamento](https://www.mercadopago.com.br/developers/pt/docs/checkout-pro/payment-notifications).

## Prévia de perfil

O navegador consulta somente a rota interna do Django:

```text
GET /api/profile-preview/?platform=instagram&target=@usuario
```

Com `PROFILE_LOOKUP_SIMULATED=True`, a resposta usa um fallback local e pede
confirmação manual. Quando houver documentação oficial, implemente o adaptador
exclusivamente em `store/services/profile_lookup.py`; a chave nunca deve ir
para o JavaScript.

## Segurança em produção

- Use HTTPS, segredo Django longo e chaves distintas por ambiente.
- Configure PostgreSQL e um cache compartilhado, como Redis, para rate limiting.
- Marque `TRUST_X_FORWARDED_FOR=True` e `TRUST_X_FORWARDED_PROTO=True` somente
  atrás de proxy confiável.
- Restrinja acesso ao Admin por rede, VPN ou camada adicional de autenticação.
- Faça backup, monitore logs e rotacione chaves periodicamente.
- Nunca grave `.env` no Git.

## Recursos comerciais

O número do suporte e as informações rotativas são configurados no `.env`:

```dotenv
WHATSAPP_SUPPORT_NUMBER=+5518996650268
SOCIAL_PROOF_ENABLED=True
```

As notificações rotativas exibem somente informações genéricas da loja. Elas
não usam pedidos, nomes ou dados reais de clientes e podem ser desativadas com
`SOCIAL_PROOF_ENABLED=False`.

Exemplo PostgreSQL:

```dotenv
POSTGRES_DB=webmaster
POSTGRES_USER=webmaster
POSTGRES_PASSWORD=senha-forte
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

No deploy:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

A migration `0004` renomeia os campos históricos do pedido sem apagar dados e
preenche `external_payment_id` a partir do log de cobrança existente.

## Testes

```bash
python manage.py check
python manage.py test
```

Os Termos de Uso incluídos devem ser revisados por profissional jurídico antes
da publicação.
