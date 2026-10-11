# Validação do Arremate

Verificações desta versão:

- Sintaxe Python e JavaScript: passou.
- Testes da API com SQLite: **9 testes passaram**.
- Uso no navegador Chromium, com desktop e celular: **passou**.

O teste no navegador percorreu login, cadastro de três funcionários, produto, criação de dois lotes com responsáveis diferentes, saída e entrada em cada perfil, confirmação obrigatória de perda, conclusão com e sem perda e relatório final.

Foi confirmado que:

1. A gerente vê todos os lotes e telas administrativas.
2. Quem não está alocado não recebe o lote pela API nem o vê na tela.
3. Quem está alocado consegue acompanhar todas as etapas do seu lote.
4. Uma etapa futura não pode iniciar antes da conclusão da anterior.
5. Um funcionário não inicia nem finaliza a etapa de outra pessoa.
6. A finalização exige resposta Sim/Não sobre perda, inclusive no servidor.
7. Com Sim, a quantidade deve ser inteira, positiva, dentro do disponível, com motivo.
8. Com Não, a perda confirmada é zero.
9. A perda de 2 em 100 peças deixa 98 para a próxima etapa.
10. O valor final para 98 peças a R$ 4,50 é R$ 441,00.
11. A ocorrência não interpreta texto informado pelo usuário como HTML.
12. O login não apaga campos durante a atualização periódica.
13. A tela funciona em 390 px de largura sem rolagem horizontal.
14. Remover a alocação retira o lote e seus avisos do funcionário.
15. A API mantém proteção de sessão/CSRF, bloqueio e redefinição de senha.
16. Transações evitam conflito entre início de etapa e perda retroativa.
17. Repetir o mesmo identificador de comando não aplica a perda duas vezes.

O HTML das telas, formulários, modais e modelos está no `static/index.html`. A checagem da API confirma esses elementos e que o JavaScript não constrói telas por `innerHTML`.

O esquema de tabelas SQLite é compatível com a versão anterior. Siga o procedimento de backup e atualização do README para aproveitar seus dados.

A conta externa PostgreSQL/Supabase não foi conectada nesta validação; é preciso configurar e conferir a conexão no seu ambiente. Dados reais da oficina não estão incluídos no ZIP.
