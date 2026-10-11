# Arremate

Sistema interno para oficina de costura. Projeto/equipe: **Arremate**.

- HTML com as telas e os formulários escritos no `index.html`.
- CSS separado para o visual.
- JavaScript puro para eventos, preenchimento dos dados e chamadas à API.
- Python sem framework no backend.
- SQLite local por padrão; PostgreSQL opcional na nuvem.

Não precisa de React, Node, npm ou compilação para rodar.

## Rodar pela primeira vez

Instale Python 3.11 ou superior. Abra o terminal na pasta `arremate`:

```powershell
python app.py init
python app.py
```

O primeiro comando cria as tabelas e pede nome, login e senha da gerente. Ao digitar a senha, ela não aparece no terminal. O segundo inicia o servidor.

Abra **http://localhost:8000**. No Windows, se `python` não funcionar, use `py`. No Linux/macOS, use `python3`.

Não abra `index.html` com duplo clique ou Live Server para usar o sistema: os dados e o login dependem do Python. Nenhuma dependência precisa ser instalada para SQLite.

O banco novo fica em `data/arremate.db`. Não existe login ou senha padrão.

## Atualizar uma instalação que já tem dados

O ZIP não contém seus dados reais. Para reaproveitar o banco SQLite da versão anterior:

1. No terminal **da versão anterior**, faça um backup consistente: 

```powershell
python app.py backup --output backup-arremate.db
```

2. Pare o servidor antigo com Ctrl+C.
3. Extraia esta versão em uma **pasta nova**.
4. Na nova pasta `arremate`, crie `data` e copie `backup-arremate.db` para `data/arremate.db`.
5. Execute `python app.py init` e `python app.py` na pasta nova.

O esquema SQLite continua compatível: os lotes, funcionários, senhas e ocorrências são preservados. O comando `init` não substitui a gerente existente. Será preciso entrar novamente porque o cookie de sessão mudou de nome.

Se seu `.env` tinha `SQLITE_PATH`, ajuste o caminho para a cópia do banco que deseja usar. Mantenha o backup e a pasta anterior até conferir os dados. Não copie apenas um arquivo de banco em uso: use o comando de backup para incluir os dados do WAL.

PostgreSQL usa agora o schema `arremate`. Se já possui dados em outro schema, faça backup e renomeie esse schema para `arremate` em vez de inicializar um banco vazio. No SQL Editor, com o nome real do schema anterior:

```sql
ALTER SCHEMA NOME_DO_SCHEMA_ANTERIOR RENAME TO arremate;
```

Não execute isso se o schema de destino já existir; primeiro confira qual contém seus dados. O novo ZIP não transfere ou mescla bancos automaticamente.

## Regras do sistema

**Gerente:** vê todos os lotes, cadastra equipe e acesso, produtos e etapas. Ao criar o lote, escolhe a sequência, responsáveis, quantidade inicial, valor por peça, entrega e datas previstas por etapa. Acompanha os resultados e todas as ocorrências.

**Funcionário:** vê somente os lotes em que está alocado em alguma etapa. Pode consultar o caminho completo desses lotes desde a atribuição. Enquanto as etapas anteriores não terminam, ele apenas acompanha. Quando chega sua vez, pode iniciar e depois finalizar. Valores e cadastros administrativos não aparecem no acesso dele.

**Finalização obrigatória:** o formulário pergunta “Houve perda de peças?” e começa sem resposta. É preciso escolher Sim ou Não. Com Sim, quantidade e motivo são obrigatórios; com Não, o sistema confirma perda zero. O Python também valida, mesmo se alguém alterar o HTML ou enviar uma requisição manual.

**Perdas:** são descontadas da saída da etapa atual e da entrada/saída prevista de todas as etapas posteriores, na mesma transação que conclui a etapa. Exemplo: 100 peças − 2 no Corte = 98 previstas para Cós, Passantes e Acabamento. Uma perda de mais 3 no Cós reduz as posteriores para 95. Perda total cancela as próximas etapas por falta de peças.

**Ocorrência posterior:** depois de concluir, o funcionário ainda pode registrar uma ocorrência enquanto ninguém iniciou as etapas seguintes. Após esse início, uma perda retroativa é bloqueada.

**Avisos:** aparecem dentro do sistema e são direcionados ao responsável. Uma atribuição avisa a pessoa; a conclusão avisa quem executará a próxima etapa. Ao retirar todas as atribuições de uma pessoa no lote, o lote e seus avisos deixam de aparecer para ela. Não existe email ou push nesta versão.

**Atualização:** consulta a API a cada 5 segundos com a aba visível. Datas das etapas são previsões manuais da gerente.

**Resultados:** total confeccionado considera lotes encerrados. Valores previstos consideram as peças restantes × valor por peça. Esta versão não registra pagamentos ou baixas financeiras.

## Onde mexer em cada coisa

| Arquivo | O que contém |
| --- | --- |
| `static/index.html` | Telas, menus, formulários, modais e modelos HTML |
| `static/style.css` | Cores, espaçamento, disposição e ajustes para celular |
| `static/app.js` | Cliques, envio dos formulários e preenchimento dos dados |
| `app.py` | Servidor, login, sessões, rotas HTTP e comandos do terminal |
| `service.py` | Regras de permissão, etapas, perdas e validações |
| `db.py` | Conexão e transações do banco |
| `database/schema.sql` | Criação das tabelas e índices |
| `tests/test_app.py` | Testes automáticos das regras |

Para estudar, comece pelo `index.html`. Depois procure no `app.js` o mesmo ID do formulário ou botão.

Exemplo: o `form-finalizar` existe no HTML. No JavaScript, seu evento `submit` lê a resposta sobre perdas e envia o comando `complete`. No `service.py`, esse comando é validado e gravado no banco.

Os `<template>` no fim do HTML são modelos de partes repetidas: cartão de lote, linha de funcionário, etapa e observação. O JavaScript usa `cloneNode` para copiá-los e `textContent` para preencher. Não existem telas inteiras em strings nem uso de `innerHTML` para gerar formulários. Isso também evita interpretar nomes e observações como código HTML.

## GitHub e colaboradores

Clonar o GitHub baixa o código, não dá acesso automático aos dados.

- Funcionários precisam apenas da URL do sistema, login e senha.
- Desenvolvedores podem executar localmente e ter seu SQLite individual.
- Para trabalhar com os mesmos dados remotamente, configure um PostgreSQL de testes compartilhado.

O `.gitignore` exclui `.env`, banco, backups e arquivos temporários. Não envie credenciais ou banco real ao GitHub.

Em um repositório novo:

```powershell
git init
git add .
git commit -m "Sistema Arremate"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

Se já clonou um repositório, use `git add`, `git commit` e `git push` normalmente.

## Usar na rede da oficina

Para testar, rode no computador que ficará como servidor:

```powershell
python app.py --host 0.0.0.0 --port 8000
```

Use `ipconfig` para encontrar o IPv4. Em outro aparelho da mesma rede, abra, por exemplo, `http://192.168.1.50:8000`, trocando pelo IP real. O computador central precisa ficar ligado. Se necessário, permita a porta 8000 no perfil privado do Firewall do Windows.

O arquivo SQLite fica junto do Python, no computador servidor. Todos os usuários passam pela API; não abra o banco diretamente em várias máquinas nem coloque o banco em pasta de rede/OneDrive para compartilhá-lo.

O servidor de `python app.py` é de desenvolvimento. Para uso contínuo com vários usuários, instale Waitress (servidor WSGI, não framework):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "waitress>=3.0.2,<4"
.\.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:8000 app:application
```

Para internet, use hospedagem Python com HTTPS. GitHub Pages não executa o backend. Em hospedagem com SQLite, o disco deve ser persistente. Não use o servidor de desenvolvimento como servidor público.

## PostgreSQL/Supabase opcional

SQLite é o caminho mais simples para estudar. Para PostgreSQL:

1. Crie o projeto em https://supabase.com e guarde a senha do banco.
2. No painel, abra **Connect** e copie a URL do **Session pooler**.
3. Troque o marcador de senha pela senha real, codificando os caracteres especiais para URL.
4. Copie `.env.example` para `.env` e instale as dependências opcionais:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-cloud.txt
```

5. Edite `.env`:

```dotenv
DATABASE_URL=postgresql://USUARIO:SENHA_CODIFICADA@HOST:5432/postgres?sslmode=require
COOKIE_SECURE=0
```

Use host, porta e usuário fornecidos pelo painel. O formato acima é apenas um exemplo. Se a URL já tiver `?`, acrescente opções com `&`.

6. Inicialize e rode:

```powershell
.\.venv\Scripts\python.exe app.py init
.\.venv\Scripts\python.exe app.py
```

As tabelas serão criadas no schema privado `arremate`. Não exponha esse schema na Data API. O navegador nunca recebe `DATABASE_URL`; ela fica no backend. Compartilhe somente a URL de um banco de testes com desenvolvedores autorizados, por um canal privado.

Trocar SQLite por PostgreSQL não copia os dados automaticamente. Esta entrega foi testada com SQLite; a conexão com sua conta Supabase precisa ser configurada e conferida por você. Consulte limites atuais do plano em https://supabase.com/pricing.

Para hospedagem HTTPS, configure `COOKIE_SECURE=1`, instale `requirements-cloud.txt` e use `waitress-serve --listen=0.0.0.0:8000 app:application`, ajustando a porta conforme o serviço.

## Backup, senha e testes

Backup SQLite consistente:

```powershell
python app.py backup --output backup-arremate.db
```

Para restaurar, pare o servidor e use o backup em uma pasta de dados limpa; preserve a instalação anterior. Não misture o backup restaurado com arquivos WAL/SHM antigos. Para PostgreSQL, use `pg_dump` do schema `arremate` com uma conexão autorizada.

Recuperar senha com acesso ao terminal do servidor:

```powershell
python app.py reset-password
```

Rodar testes SQLite (bancos temporários):

```powershell
python -m unittest discover -s tests -v
```

Para testar PostgreSQL há `TEST_DATABASE_URL`. Use somente banco descartável: os testes apagam/recriam o schema `arremate` nesse banco.

Senhas têm hash com salt; a API não devolve hashes. Sessões duram 12 horas. Bloquear acesso ou trocar a senha de um funcionário invalida suas sessões. A proteção de acesso está no Python, não apenas na visibilidade dos botões.

A API usa `/api/login`, `/api/state`, `/api/logout` e `/api/command`. POSTs usam JSON, `X-Arremate-Request` e, após login, token CSRF. Cada comando tem um identificador que evita duplicar perdas quando uma requisição é repetida.
