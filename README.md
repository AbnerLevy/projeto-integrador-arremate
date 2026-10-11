# Projeto Integrador - Arremate (Polo Têxtil do Agreste)  
Equipe: **Arremate**

Sistema de gestão voltado para o apoio operacional de microempresas e oficinas de costura (facções) do Polo de Confecções do Agreste Pernambucano. Desenvolvido como Projeto Integrador do 2º período do curso de Análise e Desenvolvimento de Sistemas do SENAC.


## 🚀 Tecnologias Utilizadas

* **Backend:** Python com Flask
* **Banco de Dados:** SQLite (desenvolvimento/testes) banco padrão / PostgreSQL (produção) opcional na nuvem.
* **Frontend:** HTML5, CSS3 e JavaScript
* **Controle de Versão:** Git e GitHub


## Rodar pela primeira vez

Instale Python 3.11 ou superior. Abra o terminal na pasta `arremate`:

```powershell
python app.py init
python app.py
```

O primeiro comando cria as tabelas e pede nome, login e senha da gerente. Ao digitar a senha, ela não aparece no terminal. O segundo inicia o servidor.

Abra **http://localhost:8000**. No Windows, se `python` não funcionar, use `py`. No Linux/macOS, use `python3`.

Não abra `index.html` com duplo clique ou Live Server para usar o sistema: os dados e o login dependem do Python. Nenhuma dependência precisa ser instalada para SQLite.

## Regras do sistema

**Gerente:** vê todos os lotes, cadastra equipe e acesso, produtos e etapas. Ao criar o lote, escolhe a sequência, responsáveis, quantidade inicial, valor por peça, entrega e datas previstas por etapa. Acompanha os resultados e todas as ocorrências.

**Funcionário:** vê somente os lotes em que está alocado em alguma etapa. Pode consultar o caminho completo desses lotes desde a atribuição. Enquanto as etapas anteriores não terminam, ele apenas acompanha. Quando chega sua vez, pode iniciar e depois finalizar. Valores e cadastros administrativos não aparecem no acesso dele.

**Finalização obrigatória:** o formulário pergunta “Houve perda de peças?” e começa sem resposta. É preciso escolher Sim ou Não. Com Sim, quantidade e motivo são obrigatórios; com Não, o sistema confirma perda zero. O Python também valida, mesmo se alguém alterar o HTML ou enviar uma requisição manual.

**Perdas:** são descontadas da saída da etapa atual e da entrada/saída prevista de todas as etapas posteriores, na mesma transação que conclui a etapa. Exemplo: 100 peças − 2 no Corte = 98 previstas para Cós, Passantes e Acabamento. Uma perda de mais 3 no Cós reduz as posteriores para 95. Perda total cancela as próximas etapas por falta de peças.

**Ocorrência posterior:** depois de concluir, o funcionário ainda pode registrar uma ocorrência enquanto ninguém iniciou as etapas seguintes. Após esse início, uma perda retroativa é bloqueada.

**Avisos:** aparecem dentro do sistema e são direcionados ao responsável. Uma atribuição avisa a pessoa; a conclusão avisa quem executará a próxima etapa. Ao retirar todas as atribuições de uma pessoa no lote, o lote e seus avisos deixam de aparecer para ela. Não existe email ou push nesta versão.

**Atualização:** consulta a API a cada 5 segundos com a aba visível. Datas das etapas são previsões manuais da gerente.

**Resultados:** total confeccionado considera lotes encerrados. Valores previstos consideram as peças restantes × valor por peça. Esta versão não registra pagamentos ou baixas financeiras.

## Arquivos principais e suas funções

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

O `.gitignore` exclui `.env`, banco, backups e arquivos temporários. Não envie credenciais ou banco real ao GitHub.

## Usar na rede da oficina

Para testar, rode no computador que ficará como servidor:

```powershell
python app.py --host 0.0.0.0 --port 8000
```

Use `ipconfig` para encontrar o IPv4 do servidor. Em outro aparelho certifique-se de está na mesma rede do servidor, abra por exemplo, `http://192.168.X.XX:8000`, trocando os X.XX pelo IP real do servidor. O servidor precisa ficar ligado. Se necessário, permita a porta 8000 no perfil privado do Firewall do Windows.

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

As tabelas serão criadas no schema privado `arremate`.

Trocar SQLite por PostgreSQL não copia os dados automaticamente.

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
