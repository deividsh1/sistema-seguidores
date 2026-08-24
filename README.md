# WebMaster

Loja desenvolvida com **Django** em formato de landing page + catálogo, criada para demonstrar um fluxo completo de venda de serviços digitais.

O projeto permite selecionar pacotes, confirmar um perfil, realizar um checkout e acompanhar o processamento do pedido, com suporte a pagamentos Pix e integração com fornecedor externo.

> **Status:** projeto acadêmico/portfólio. As integrações externas podem ser executadas em modo simulado para desenvolvimento local.

## ✨ Funcionalidades

* Landing page com benefícios, FAQ, depoimentos e chamadas para ação.
* Catálogo separado para Instagram e TikTok.
* Sistema de serviços e pacotes configurável pelo Django Admin.
* Preços e quantidades definidos no servidor.
* Checkout sem necessidade de criação de conta.
* Confirmação de perfil antes da compra.
* Aceite dos Termos de Uso com registro da versão e informações da sessão.
* Carrinho com serviços complementares.
* Validação dos preços e do total diretamente no servidor.
* Suporte a comentários personalizados.
* Processamento de pedidos com estados independentes por item.
* Integração com pagamentos Pix.
* Webhook para atualização do status de pagamento.
* Integração com fornecedor externo para processamento dos pedidos.
* Modo simulado para desenvolvimento sem realizar cobranças ou chamadas externas.
* Prévia de perfil através de uma rota interna da aplicação.
* Rate limiting para operações sensíveis.
* Sanitização de respostas externas antes do armazenamento em logs.
* SQLite para desenvolvimento e suporte a PostgreSQL.
* Cache local com possibilidade de utilização de cache compartilhado em ambientes com múltiplos processos.

---

## 🏗️ Arquitetura

O projeto utiliza Django seguindo uma separação entre:

* **Models** — persistência e relacionamento dos dados.
* **Views** — controle das requisições e respostas.
* **Templates** — interface da aplicação.
* **Services** — integrações e regras relacionadas a serviços externos.
* **Forms** — validação dos dados enviados pelo usuário.
* **Admin** — gerenciamento do catálogo e dos pedidos.
* **Static** — CSS e JavaScript da interface.

### Principais entidades

```text
Platform
   │
   └── Service
          │
          └── Package

Order
   │
   └── OrderItem
          │
          └── Package

PaymentLog
ProviderLog
```

### Modelos principais

* `Platform` — plataforma disponível no catálogo.
* `Service` — tipo de serviço oferecido.
* `Package` — quantidade e preço de cada serviço.
* `Order` — pedido realizado pelo cliente.
* `OrderItem` — itens individuais de um pedido.
* `PaymentLog` — histórico relacionado ao pagamento.
* `ProviderLog` — histórico da comunicação com o fornecedor.

---

## 🛒 Catálogo

O catálogo é administrado através do **Django Admin**.

Cada serviço pode possuir:

* nome;
* descrição;
* identificador técnico;
* quantidade mínima;
* quantidade máxima;
* disponibilidade;
* configuração para comentários personalizados.

Os pacotes possuem:

* quantidade;
* preço;
* destaque;
* disponibilidade.

Os valores são controlados pelo servidor e não dependem do preço enviado pelo navegador.

### Histórico dos pedidos

No momento da compra, informações importantes são armazenadas no pedido.

Isso inclui, por exemplo:

* quantidade;
* preço;
* identificador técnico do serviço;
* informações relacionadas ao pagamento.

Dessa forma, alterações futuras no catálogo não modificam o histórico de pedidos existentes.

---

## 🛍️ Carrinho

O checkout permite adicionar serviços complementares da mesma plataforma.

O sistema limita a quantidade de complementos e impede combinações inválidas.

O JavaScript atualiza o resumo visual do carrinho, mas o Django **recalcula e valida os valores no servidor** antes de criar o pedido.

Isso evita que o preço exibido no navegador seja utilizado como fonte de verdade.

---

## 💬 Comentários personalizados

Alguns serviços podem exigir comentários personalizados.

Nesse caso:

* o cliente informa um comentário por linha;
* linhas vazias são ignoradas;
* a quantidade de comentários é validada;
* os comentários somente são enviados ao fornecedor após a confirmação do pagamento.

---

## 💳 Pagamentos

O projeto possui uma camada de serviço responsável pela integração com pagamentos Pix.

A implementação está localizada em:

```text
store/services/payment_api.py
```

Entre as principais operações estão:

```python
create_pix_charge(order)
get_payment_status(external_payment_id)
parse_payment_webhook(request)
```

O fluxo foi desenvolvido para:

1. criar a cobrança;
2. armazenar o identificador externo;
3. receber notificações;
4. validar a notificação;
5. consultar o pagamento;
6. confirmar o status diretamente no provedor;
7. liberar o processamento do pedido somente após a confirmação.

O projeto também possui **modo simulado**, permitindo testar o fluxo sem realizar pagamentos reais.

---

## 🔌 Integração com fornecedor

A comunicação com o fornecedor externo está isolada em:

```text
store/services/provider_api.py
```

Operações suportadas:

```text
services
add
status
refill
cancel
balance
```

A aplicação separa essa integração do restante da lógica da loja, facilitando a substituição ou alteração do fornecedor futuramente.

As credenciais de integração são obtidas através de variáveis de ambiente e não ficam armazenadas no código-fonte.

---

## 👤 Prévia de perfil

A aplicação possui uma rota interna para consulta de perfil:

```text
GET /api/profile-preview/?platform=instagram&target=@usuario
```

A consulta é intermediada pelo backend para evitar que credenciais de serviços externos sejam expostas ao navegador.

Durante o desenvolvimento, pode ser utilizado um modo simulado com fallback local.

---

## 🔐 Segurança

Algumas medidas implementadas no projeto:

* validação de dados no servidor;
* validação dos preços no backend;
* proteção contra alterações indevidas do valor do pedido;
* autenticação de webhooks;
* consulta direta do pagamento antes da aprovação;
* processamento idempotente de notificações;
* rate limiting em operações sensíveis;
* sanitização de respostas externas antes do armazenamento;
* separação de credenciais através de variáveis de ambiente;
* proteção CSRF;
* histórico imutável de informações importantes do pedido.

As configurações específicas de produção não fazem parte deste projeto de demonstração.

---

## ⚙️ Configuração

O projeto utiliza variáveis de ambiente.

Para começar:

```bash
cp .env.example .env
```

O arquivo `.env.example` contém apenas a estrutura necessária para configurar a aplicação localmente.

**Credenciais reais não fazem parte do repositório.**

Para desenvolvimento, as integrações externas podem permanecer em modo simulado.

---

## 🚀 Instalação

### 1. Clonar o projeto

```bash
git clone <URL_DO_REPOSITORIO>
cd WebMaster
```

### 2. Criar o ambiente virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

No Windows:

```powershell
.venv\Scripts\activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar o ambiente

```bash
cp .env.example .env
```

### 5. Executar as migrations

```bash
python manage.py migrate
```

### 6. Criar usuário administrativo

```bash
python manage.py createsuperuser
```

### 7. Criar dados de demonstração

```bash
python manage.py seed_demo
```

### 8. Executar o servidor

```bash
python manage.py runserver
```

A aplicação ficará disponível localmente no endereço padrão do Django.

O painel administrativo pode ser acessado através da rota:

```text
/admin/
```

---

## 🧪 Testes

Para verificar a configuração:

```bash
python manage.py check
```

Para executar a suíte de testes:

```bash
python manage.py test
```

---

## 🧩 Modo de desenvolvimento

O projeto foi estruturado para que partes que dependem de serviços externos possam ser simuladas.

Isso permite desenvolver e testar:

* criação de pedidos;
* checkout;
* cálculo de valores;
* fluxo de pagamento;
* atualização de status;
* processamento dos itens;
* integração com fornecedor;

sem depender constantemente de APIs externas.

Um pedido de demonstração pode ser criado através da aplicação e seu pagamento pode ser simulado utilizando o comando administrativo disponível no projeto.

---

## 📁 Estrutura simplificada

```text
WebMaster/
│
├── manage.py
├── requirements.txt
├── .env.example
│
├── store/
│   ├── admin.py
│   ├── forms.py
│   ├── models.py
│   ├── views.py
│   │
│   ├── services/
│   │   ├── catalog.py
│   │   ├── payment_api.py
│   │   ├── provider_api.py
│   │   ├── order_processing.py
│   │   └── profile_lookup.py
│   │
│   └── ...
│
├── templates/
│   └── store/
│
├── static/
│   ├── css/
│   └── js/
│
└── ...
```

---

## 🗃️ Banco de dados

O projeto utiliza SQLite durante o desenvolvimento.

A estrutura também foi preparada para utilização com PostgreSQL.

As migrations preservam os dados históricos dos pedidos durante alterações na estrutura dos modelos.

---

## 🎯 Objetivo do projeto

O WebMaster foi desenvolvido como um projeto de **portfólio para demonstrar desenvolvimento web com Django**, incluindo:

* desenvolvimento backend;
* modelagem de banco de dados;
* criação de APIs internas;
* integração com APIs externas;
* processamento de pagamentos;
* webhooks;
* validação de dados;
* gerenciamento de pedidos;
* arquitetura baseada em serviços;
* segurança de aplicações web;
* desenvolvimento de interfaces responsivas.

O projeto busca demonstrar não apenas a criação de páginas, mas a implementação de um **fluxo completo de aplicação web**, desde o catálogo até o processamento de um pedido.

---

## 📚 Tecnologias

* Python
* Django
* SQLite
* PostgreSQL
* HTML
* CSS
* JavaScript
* REST APIs
* Webhooks
* Pix
* Git

---

## 📄 Licença

Este projeto está disponível para fins de estudo e portfólio.

Consulte o arquivo `LICENSE` para obter os termos de utilização do código.

---

## 👨‍💻 Autor

**Deivid**

Projeto desenvolvido como parte do processo de aprendizado e construção de portfólio em desenvolvimento de software.
