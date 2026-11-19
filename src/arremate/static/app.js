/* Arremate: JavaScript sem framework.
   O HTML está no index.html. Aqui buscamos dados e ligamos os botões às ações. */

let dados = null;
let telaAtual = 'lotes';
let loteAberto = null;
let salvando = false;
let atualizando = false;
let tentativaPendente = null;
let tempoMensagem;

const nomesStatus = {
  waiting: 'Aguardando',
  ready: 'Disponível',
  active: 'Em andamento',
  done: 'Concluída',
  cancelled: 'Sem peças'
};

// 1. Funções pequenas para trabalhar com o HTML.
function elemento(id) {
  return document.getElementById(id);
}

function copiarModelo(id) {
  return elemento(id).content.firstElementChild.cloneNode(true);
}

function escrever(modelo, classe, valor) {
  modelo.querySelector(classe).textContent = valor;
}

function moeda(centavos) {
  return (centavos / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function dataCurta(data) {
  if (!data) return 'Sem previsão';
  return new Date(data + 'T12:00:00').toLocaleDateString('pt-BR');
}

function dataHora(data) {
  return new Date(data).toLocaleString('pt-BR');
}

function ehGerente() {
  return dados && dados.me.role === 'manager';
}

function nomePessoa(id) {
  const pessoa = dados.members.find(function (pessoa) { return pessoa.id === id; });
  return pessoa ? pessoa.name : 'Equipe';
}

function preencherSelect(select, itens, escolhido, titulo) {
  select.replaceChildren();
  select.add(new Option(titulo, ''));
  for (const item of itens) {
    select.add(new Option(item.name, item.id));
  }
  select.value = escolhido || '';
}

function pessoasLiberadas() {
  return dados.members.filter(function (pessoa) { return pessoa.role === 'worker' && pessoa.enabled === 1; });
}

function lerFormulario(formulario) {
  return Object.fromEntries(new FormData(formulario));
}

function mostrarMensagem(texto, erro = false) {
  const caixa = elemento('mensagem');
  const modal = document.querySelector('dialog[open]');
  // Dentro do modal, a mensagem fica visível acima do fundo escurecido.
  if (modal) modal.append(caixa);
  else document.body.append(caixa);
  caixa.textContent = texto;
  caixa.classList.toggle('erro', erro);
  caixa.hidden = false;
  clearTimeout(tempoMensagem);
  tempoMensagem = setTimeout(function () { caixa.hidden = true; }, 6000);
}

function fecharModais() {
  for (const modal of document.querySelectorAll('dialog[open]')) {
    modal.close();
  }
  document.body.append(elemento('mensagem'));
}

function abrirModal(id) {
  fecharModais();
  elemento(id).showModal();
}

// 2. Comunicação com o Python. As permissões também são verificadas no servidor.
async function chamarAPI(caminho, corpo) {
  const opcoes = { credentials: 'same-origin', cache: 'no-store' };
  if (corpo !== undefined) {
    opcoes.method = 'POST';
    opcoes.headers = {
      'Content-Type': 'application/json',
      'X-Arremate-Request': '1',
      'X-CSRF-Token': dados ? dados.csrf : ''
    };
    opcoes.body = JSON.stringify(corpo);
  }
  const resposta = await fetch(caminho, opcoes);
  const resultado = await resposta.json();
  if (!resposta.ok) {
    if (resposta.status === 401 && caminho !== '/api/login') mostrarLogin();
    throw new Error(resultado.error || 'Não foi possível salvar.');
  }
  return resultado;
}

function novoIdentificador() {
  // Evita repetir uma operação quando a conexão falha e a pessoa tenta de novo.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, function (numero) { return numero.toString(16).padStart(2, '0'); }).join('');
}

async function enviarComando(comando, voltarAoLote = false) {
  if (salvando) return false;
  salvando = true;
  // Guardar o estado dos botões evita habilitar algum que já estava bloqueado.
  const botoes = Array.from(document.querySelectorAll('button'));
  const estados = botoes.map(function (botao) { return botao.disabled; });
  for (const botao of botoes) botao.disabled = true;
  try {
    const assinatura = JSON.stringify(comando);
    if (!tentativaPendente || tentativaPendente.assinatura !== assinatura) {
      tentativaPendente = { assinatura: assinatura, id: novoIdentificador() };
    }
    comando.request_id = tentativaPendente.id;
    dados = await chamarAPI('/api/command', comando);
    tentativaPendente = null;
    fecharModais();
    atualizarTelas();
    if (voltarAoLote && loteAberto) abrirDetalheLote(loteAberto);
    mostrarMensagem('Salvo com sucesso.');
    return true;
  } catch (erro) {
    mostrarMensagem(erro.message, true);
    return false;
  } finally {
    salvando = false;
    botoes.forEach(function (botao, indice) { botao.disabled = estados[indice]; });
  }
}

async function buscarDados() {
  if (salvando || atualizando) return;
  if (!dados && !elemento('tela-login').hidden) return;
  atualizando = true;
  const usuarioAntes = dados ? dados.me.id : null;
  try {
    const resposta = await chamarAPI('/api/state');
    // Uma consulta antiga não pode substituir o resultado de uma ação recém-salva.
    if (salvando || (usuarioAntes && !dados)) return;
    if (dados && usuarioAntes && usuarioAntes !== dados.me.id) return;
    if (dados && resposta.revision < dados.revision) return;
    dados = resposta;
    atualizarTelas();
    const modalLote = elemento('modal-lote');
    if (modalLote.open && loteAberto) preencherDetalheLote(loteAberto);
    if (elemento('modal-avisos').open) preencherAvisos();
    elemento('atualizacao').textContent = 'Atualizado agora · consulta a cada 5 segundos';
  } catch (erro) {
    if (dados) {
      elemento('atualizacao').textContent = 'Sem conexão. Tentando novamente…';
    } else if (elemento('tela-login').hidden) {
      elemento('carregando').hidden = true;
      elemento('erro-conexao').hidden = false;
    }
  } finally {
    atualizando = false;
  }
}

// 3. Telas estáticas: usamos hidden para escolher o que aparece.
function mostrarLogin() {
  dados = null;
  loteAberto = null;
  tentativaPendente = null;
  telaAtual = 'lotes';
  fecharModais();
  elemento('carregando').hidden = true;
  elemento('erro-conexao').hidden = true;
  elemento('sistema').hidden = true;
  elemento('tela-login').hidden = false;
  elemento('form-login').reset();
}

function mostrarTela(nome) {
  if (!ehGerente() && nome !== 'lotes') return;
  telaAtual = nome;
  for (const tela of ['lotes', 'equipe', 'cadastros', 'resultados']) {
    elemento('tela-' + tela).hidden = tela !== nome;
    elemento('menu-' + tela).classList.toggle('ativo', tela === nome);
  }
}

function atualizarTelas() {
  elemento('carregando').hidden = true;
  elemento('erro-conexao').hidden = true;
  elemento('tela-login').hidden = true;
  elemento('sistema').hidden = false;
  elemento('nome-usuario').textContent = dados.me.name;
  elemento('funcao-usuario').textContent = ehGerente() ? 'Gerente' : dados.me.specialty;
  elemento('tipo-painel').textContent = ehGerente() ? 'PAINEL DA GERENTE' : 'PAINEL DO FUNCIONÁRIO';
  elemento('titulo-lotes').textContent = ehGerente() ? 'Produção' : 'Meus lotes';
  elemento('descricao-lotes').textContent = ehGerente() ? 'Crie os lotes e acompanhe cada etapa.' : 'Acompanhe os lotes em que você foi alocado e execute sua etapa quando chegar sua vez.';
  for (const item of document.querySelectorAll('.somente-gerente')) item.hidden = !ehGerente();
  const naoLidos = dados.notices.filter(function (aviso) { return !aviso.seen; }).length;
  elemento('numero-avisos').textContent = naoLidos ? '(' + naoLidos + ')' : '';
  preencherLotes();
  if (ehGerente()) {
    preencherEquipe();
    preencherCadastros();
    preencherResultados();
  }
  mostrarTela(telaAtual);
}

function preencherLotes() {
  const lista = elemento('lista-lotes');
  lista.replaceChildren();
  const busca = elemento('busca-lotes').value.toLowerCase();
  const filtro = elemento('filtro-lotes').value;
  for (const lote of dados.batches) {
    const texto = (lote.code + ' ' + lote.product + ' ' + lote.color).toLowerCase();
    const atual = lote.tasks.find(function (etapa) { return etapa.status === 'ready' || etapa.status === 'active'; });
    const minhaVez = atual && atual.assignee_id === dados.me.id;
    if (!texto.includes(busca)) continue;
    if (filtro === 'minha-vez' && !minhaVez) continue;
    if (filtro === 'producao' && lote.finished) continue;
    if (filtro === 'concluidos' && !lote.finished) continue;
    const cartao = copiarModelo('modelo-lote');
    escrever(cartao, '.codigo', lote.code);
    escrever(cartao, '.produto', lote.product);
    escrever(cartao, '.cor-tamanhos', (lote.color || 'Sem cor') + ' · ' + (lote.sizes || 'Sem tamanhos'));
    escrever(cartao, '.situacao', lote.finished ? 'Encerrado' : nomesStatus[atual ? atual.status : 'waiting']);
    cartao.querySelector('.situacao').classList.add(lote.finished ? 'done' : (atual ? atual.status : 'waiting'));
    escrever(cartao, '.nome-etapa', lote.finished ? 'Lote encerrado' : (atual ? atual.name : 'Aguardando'));
    escrever(cartao, '.quantidade', lote.remaining + ' peças previstas');
    escrever(cartao, '.entrega', dataCurta(lote.due_date));
    const progresso = cartao.querySelector('.progresso');
    progresso.max = lote.tasks.length;
    progresso.value = lote.tasks.filter(function (etapa) { return etapa.status === 'done' || etapa.status === 'cancelled'; }).length;
    cartao.querySelector('.sua-vez').hidden = !minhaVez;
    cartao.addEventListener('click', function () { abrirDetalheLote(lote.id); });
    lista.append(cartao);
  }
  elemento('sem-lotes').hidden = lista.childElementCount > 0;
}

function abrirDetalheLote(id) {
  loteAberto = id;
  if (preencherDetalheLote(id)) abrirModal('modal-lote');
}

function preencherDetalheLote(id) {
  const lote = dados.batches.find(function (lote) { return lote.id === id; });
  if (!lote) {
    fecharModais();
    mostrarMensagem('Este lote não está mais atribuído a você.');
    return false;
  }
  elemento('titulo-detalhe').textContent = lote.code + ' · ' + lote.product;
  elemento('descricao-detalhe').textContent = lote.color + ' · ' + lote.sizes + (ehGerente() ? ' · ' + lote.client : '');
  elemento('quantidade-detalhe').textContent = lote.quantity;
  elemento('perdas-detalhe').textContent = lote.lost;
  elemento('entrega-detalhe').textContent = dataCurta(lote.due_date);
  const precoPeca = elemento('preco-peca-detalhe');
  precoPeca.closest('.valor-lote').hidden = !ehGerente();
  if (ehGerente()) precoPeca.textContent = moeda(lote.price_cents);
  elemento('financeiro-detalhe').hidden = !ehGerente();
  elemento('notas-detalhe').hidden = !ehGerente() || !lote.notes;
  elemento('notas-detalhe').textContent = lote.notes || '';
  if (ehGerente()) elemento('valor-detalhe').textContent = moeda(lote.remaining * lote.price_cents);
  const lista = elemento('etapas-detalhe');
  lista.replaceChildren();
  lote.tasks.forEach(function (etapa, indice) {
    const linha = copiarModelo('modelo-etapa-detalhe');
    const minha = etapa.assignee_id === dados.me.id;
    linha.classList.add(etapa.status);
    escrever(linha, '.numero-etapa', etapa.status === 'done' ? '✓' : indice + 1);
    escrever(linha, '.nome', etapa.name);
    escrever(linha, '.responsavel-status', nomePessoa(etapa.assignee_id) + ' · ' + nomesStatus[etapa.status]);
    escrever(linha, '.quantidades', 'Entrada: ' + etapa.incoming + ' · Saída prevista: ' + etapa.outgoing);
    escrever(linha, '.previsao', 'Previsão: ' + dataCurta(etapa.planned_date));
    linha.querySelector('.sua-etapa').hidden = !minha;
    linha.querySelector('.inicio').hidden = !etapa.started_at;
    linha.querySelector('.fim').hidden = !etapa.completed_at;
    if (etapa.started_at) escrever(linha, '.inicio', 'Início: ' + dataHora(etapa.started_at));
    if (etapa.completed_at) escrever(linha, '.fim', 'Fim: ' + dataHora(etapa.completed_at));
    const iniciar = linha.querySelector('.iniciar');
    iniciar.hidden = !minha || etapa.status !== 'ready';
    iniciar.addEventListener('click', function () { enviarComando({ type: 'start', task_id: etapa.id }, true); });
    const finalizar = linha.querySelector('.finalizar');
    finalizar.hidden = !minha || etapa.status !== 'active';
    finalizar.addEventListener('click', function () { abrirFinalizacao(etapa); });
    const seguintes = lote.tasks.slice(indice + 1);
    const podeObservar = seguintes.every(function (proxima) { return ['waiting', 'ready', 'cancelled'].includes(proxima.status); });
    const ocorrencia = linha.querySelector('.ocorrencia');
    ocorrencia.hidden = !minha || etapa.status !== 'done' || !podeObservar;
    ocorrencia.addEventListener('click', function () {
      const form = elemento('form-ocorrencia');
      form.reset();
      form.elements.task_id.value = etapa.id;
      form.elements.quantity.max = etapa.outgoing;
      abrirModal('modal-ocorrencia');
    });
    const atribuir = linha.querySelector('.atribuir');
    atribuir.hidden = !ehGerente() || !['waiting', 'ready'].includes(etapa.status);
    atribuir.addEventListener('click', function () {
      const form = elemento('form-responsavel');
      form.elements.task_id.value = etapa.id;
      preencherSelect(form.elements.assignee_id, pessoasLiberadas(), etapa.assignee_id, 'Selecione');
      abrirModal('modal-responsavel');
    });
    lista.append(linha);
  });
  const ocorrencias = dados.losses.filter(function (ocorrencia) { return ocorrencia.batch_id === id; });
  elemento('titulo-ocorrencias').hidden = ocorrencias.length === 0;
  preencherObservacoes('ocorrencias-detalhe', ocorrencias);
  return true;
}

function preencherEquipe() {
  const lista = elemento('lista-equipe');
  lista.replaceChildren();
  for (const pessoa of dados.members) {
    if (pessoa.role !== 'worker') continue;
    const linha = copiarModelo('modelo-funcionario');
    escrever(linha, '.nome', pessoa.name);
    escrever(linha, '.funcao-login', pessoa.specialty + ' · ' + pessoa.username);
    escrever(linha, '.acesso', pessoa.enabled ? 'Acesso liberado' : 'Acesso bloqueado');
    linha.querySelector('.acesso').addEventListener('click', function () {
      enviarComando({ type: 'toggle-access', member_id: pessoa.id });
    });
    linha.querySelector('.trocar-senha').addEventListener('click', function () {
      const form = elemento('form-senha');
      form.reset();
      form.elements.member_id.value = pessoa.id;
      elemento('titulo-senha').textContent = 'Nova senha para ' + pessoa.name;
      abrirModal('modal-senha');
    });
    lista.append(linha);
  }
  elemento('sem-equipe').hidden = lista.childElementCount > 0;
}

function preencherCadastros() {
  elemento('lista-etapas').replaceChildren();
  for (const etapa of dados.stages) {
    const linha = copiarModelo('modelo-etapa-cadastro');
    escrever(linha, '.nome', etapa.name);
    escrever(linha, '.setor', etapa.sector);
    linha.querySelector('.editar').addEventListener('click', function () {
      const form = elemento('form-editar-etapa');
      form.elements.stage_id.value = etapa.id;
      form.elements.name.value = etapa.name;
      form.elements.sector.value = etapa.sector;
      abrirModal('modal-editar-etapa');
    });
    linha.querySelector('.remover').addEventListener('click', function () {
      if (confirm('Remover do catálogo? Os lotes existentes mantêm a etapa.')) enviarComando({ type: 'remove-stage', stage_id: etapa.id });
    });
    elemento('lista-etapas').append(linha);
  }
  elemento('lista-produtos').replaceChildren();
  elemento('produtos-cadastrados').replaceChildren();
  for (const produto of dados.products) {
    const linha = copiarModelo('modelo-produto');
    escrever(linha, '.nome', produto.name);
    escrever(linha, '.valor', moeda(produto.price_cents));
    elemento('lista-produtos').append(linha);
    elemento('produtos-cadastrados').append(new Option(produto.name, produto.name));
  }
}

function preencherResultados() {
  let confeccionado = 0;
  let perdas = 0;
  let valorConcluido = 0;
  let valorPrevisto = 0;
  elemento('tabela-resultados').replaceChildren();
  for (const lote of dados.batches) {
    const valor = lote.remaining * lote.price_cents;
    perdas += lote.lost;
    valorPrevisto += valor;
    if (lote.finished) {
      confeccionado += lote.remaining;
      valorConcluido += valor;
    }
    const linha = copiarModelo('modelo-resultado');
    escrever(linha, '.codigo', lote.code);
    escrever(linha, '.produto', lote.product);
    escrever(linha, '.confeccionado', lote.finished ? lote.remaining : 'Em produção');
    escrever(linha, '.perdas', lote.lost);
    escrever(linha, '.valor', moeda(valor));
    linha.querySelector('.codigo').addEventListener('click', function () { abrirDetalheLote(lote.id); });
    elemento('tabela-resultados').append(linha);
  }
  elemento('total-confeccionado').textContent = confeccionado + ' peças';
  elemento('total-perdas').textContent = perdas + ' peças';
  elemento('valor-concluido').textContent = moeda(valorConcluido);
  elemento('valor-previsto').textContent = moeda(valorPrevisto);
  preencherObservacoes('observacoes-resultados', dados.losses);
  elemento('sem-observacoes').hidden = dados.losses.length > 0;
}

function preencherObservacoes(id, ocorrencias) {
  const lista = elemento(id);
  lista.replaceChildren();
  for (const ocorrencia of ocorrencias) {
    const lote = dados.batches.find(function (lote) { return lote.id === ocorrencia.batch_id; });
    const item = copiarModelo('modelo-observacao');
    escrever(item, '.titulo', (lote ? lote.code : '') + ' · ' + ocorrencia.quantity + ' peça(s) perdida(s)');
    escrever(item, '.motivo', ocorrencia.reason);
    escrever(item, '.autor-data', nomePessoa(ocorrencia.actor_id) + ' · ' + dataHora(ocorrencia.created_at));
    lista.append(item);
  }
}

function preencherAvisos() {
  const lista = elemento('lista-avisos');
  lista.replaceChildren();
  for (const aviso of dados.notices) {
    const item = copiarModelo('modelo-aviso');
    escrever(item, '.texto', (aviso.seen ? '' : '● ') + aviso.message);
    escrever(item, '.data', dataHora(aviso.created_at));
    item.querySelector('.ver-lote').addEventListener('click', function () { abrirDetalheLote(aviso.batch_id); });
    lista.append(item);
  }
  elemento('sem-avisos').hidden = dados.notices.length > 0;
}

// 4. Montar a sequência de um novo lote copiando o template do HTML.
function adicionarEtapaLote(etapaId) {
  const linha = copiarModelo('modelo-etapa-lote');
  preencherSelect(linha.querySelector('[name="stage_id"]'), dados.stages, etapaId, 'Selecione a etapa');
  preencherSelect(linha.querySelector('[name="assignee_id"]'), pessoasLiberadas(), '', 'Selecione a pessoa');
  linha.querySelector('.remover').addEventListener('click', function () { linha.remove(); });
  linha.querySelector('.subir').addEventListener('click', function () {
    if (linha.previousElementSibling) linha.parentNode.insertBefore(linha, linha.previousElementSibling);
  });
  linha.querySelector('.descer').addEventListener('click', function () {
    if (linha.nextElementSibling) linha.parentNode.insertBefore(linha.nextElementSibling, linha);
  });
  elemento('etapas-novo-lote').append(linha);
}

function abrirFinalizacao(etapa) {
  const form = elemento('form-finalizar');
  form.reset();
  form.elements.task_id.value = etapa.id;
  form.elements.quantity.max = etapa.outgoing;
  elemento('titulo-finalizar').textContent = 'Finalizar ' + etapa.name;
  elemento('resumo-finalizar').textContent = 'Confira as ' + etapa.outgoing + ' peças e informe se houve perda.';
  configurarCamposPerda();
  abrirModal('modal-finalizar');
}

function configurarCamposPerda() {
  const form = elemento('form-finalizar');
  const houve = form.elements.had_loss.value === 'sim';
  elemento('campos-perda').hidden = !houve;
  form.elements.quantity.disabled = !houve;
  form.elements.reason.disabled = !houve;
  form.elements.quantity.required = houve;
  form.elements.reason.required = houve;
  if (!houve) {
    form.elements.quantity.value = '';
    form.elements.reason.value = '';
  }
}

// 5. Eventos dos menus, dos botões fixos e dos formulários do index.html.
for (const nome of ['lotes', 'equipe', 'cadastros', 'resultados']) {
  elemento('menu-' + nome).addEventListener('click', function () { mostrarTela(nome); });
}
for (const botao of document.querySelectorAll('.fechar')) {
  botao.addEventListener('click', fecharModais);
}
for (const modal of document.querySelectorAll('dialog')) {
  modal.addEventListener('close', function () {
    // Um evento de fechamento antigo não deve retirar a mensagem de outro modal aberto.
    if (!document.querySelector('dialog[open]')) document.body.append(elemento('mensagem'));
  });
}
elemento('busca-lotes').addEventListener('input', preencherLotes);
elemento('filtro-lotes').addEventListener('change', preencherLotes);
elemento('houve-perda').addEventListener('change', configurarCamposPerda);
elemento('tentar-novamente').addEventListener('click', buscarDados);
elemento('adicionar-etapa-lote').addEventListener('click', function () { adicionarEtapaLote(); });
elemento('novo-funcionario').addEventListener('click', function () {
  elemento('form-funcionario').reset();
  abrirModal('modal-funcionario');
});
elemento('novo-lote').addEventListener('click', function () {
  if (!dados.stages.length) return mostrarMensagem('Cadastre uma etapa antes de criar o lote.', true);
  elemento('form-lote').reset();
  elemento('etapas-novo-lote').replaceChildren();
  for (const etapa of dados.stages) adicionarEtapaLote(etapa.id);
  abrirModal('modal-novo-lote');
});
elemento('form-lote').elements.product.addEventListener('change', function (evento) {
  const produto = dados.products.find(function (produto) { return produto.name === evento.target.value; });
  if (produto) elemento('form-lote').elements.price.value = (produto.price_cents / 100).toFixed(2);
});
elemento('abrir-avisos').addEventListener('click', function () {
  preencherAvisos();
  abrirModal('modal-avisos');
});
elemento('ler-avisos').addEventListener('click', function () { enviarComando({ type: 'read-notices' }); });
elemento('sair').addEventListener('click', async function () {
  if (salvando) return;
  salvando = true;
  try {
    await chamarAPI('/api/logout', {});
    mostrarLogin();
  } catch (erro) {
    mostrarMensagem(erro.message, true);
  } finally {
    salvando = false;
  }
});

elemento('form-login').addEventListener('submit', async function (evento) {
  evento.preventDefault();
  if (salvando) return;
  salvando = true;
  const botao = this.querySelector('button');
  botao.disabled = true;
  try {
    await chamarAPI('/api/login', lerFormulario(this));
    dados = await chamarAPI('/api/state');
    atualizarTelas();
    elemento('atualizacao').textContent = 'Atualizado agora · consulta a cada 5 segundos';
    this.reset();
  } catch (erro) {
    mostrarMensagem(erro.message, true);
  } finally {
    salvando = false;
    botao.disabled = false;
  }
});

elemento('form-funcionario').addEventListener('submit', function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  valores.type = 'add-member';
  enviarComando(valores);
});
elemento('form-etapa').addEventListener('submit', async function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  valores.type = 'add-stage';
  if (await enviarComando(valores)) this.reset();
});
elemento('form-produto').addEventListener('submit', async function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  valores.type = 'add-product';
  if (await enviarComando(valores)) this.reset();
});
elemento('form-editar-etapa').addEventListener('submit', function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  valores.type = 'edit-stage';
  enviarComando(valores);
});
elemento('form-senha').addEventListener('submit', function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  valores.type = 'reset-password';
  enviarComando(valores);
});
elemento('form-responsavel').addEventListener('submit', function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  valores.type = 'assign';
  enviarComando(valores, true);
});
elemento('form-lote').addEventListener('submit', function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  valores.type = 'create-batch';
  valores.quantity = Number(valores.quantity);
  valores.stages = [];
  for (const linha of elemento('etapas-novo-lote').children) {
    valores.stages.push({
      stage_id: linha.querySelector('[name="stage_id"]').value,
      assignee_id: linha.querySelector('[name="assignee_id"]').value,
      planned_date: linha.querySelector('[name="planned_date"]').value
    });
  }
  enviarComando(valores);
});
elemento('form-finalizar').addEventListener('submit', function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  // O atributo required valida no HTML. A API valida novamente no Python.
  if (!valores.had_loss) return mostrarMensagem('Informe se houve perda.', true);
  const houve = valores.had_loss === 'sim';
  enviarComando({
    type: 'complete',
    task_id: valores.task_id,
    had_loss: houve,
    quantity: houve ? Number(valores.quantity) : 0,
    reason: houve ? valores.reason : ''
  }, true);
});
elemento('form-ocorrencia').addEventListener('submit', function (evento) {
  evento.preventDefault();
  const valores = lerFormulario(this);
  valores.type = 'loss';
  valores.quantity = Number(valores.quantity);
  enviarComando(valores, true);
});

// Primeira consulta e atualização periódica. O login não é recriado enquanto se digita.
buscarDados();
setInterval(function () {
  if (document.visibilityState === 'visible') buscarDados();
}, 5000);
