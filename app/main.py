"""Aplicação web do PWM: painel, check-in mensal e gestão de plataformas."""
from __future__ import annotations

import signal
import time
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import backup, calc, categorias, checkin, configuracao, dashboard, db, indices, plataformas

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["eur"] = calc.formatar_euros
templates.env.filters["mes"] = calc.formatar_mes


def _pct(valor: float, unidade: str = " %") -> str:
    """1.234 -> '+1,23 %' (com sinal, vírgula decimal; o menos é o sinal tipográfico)."""
    texto = f"{abs(valor):.2f}".replace(".", ",")
    sinal = "+" if valor > 0 else ("−" if valor < 0 and texto != "0,00" else "")
    return f"{sinal}{texto}{unidade}"


templates.env.filters["pct"] = _pct
templates.env.filters["pp"] = lambda v: _pct(v, " p.p.")

AVISOS = {
    calc.AVISO_GANHO_NEGATIVO: "Ganho negativo: confirma o saldo e o aporte (erro de registo ou perda real).",
    calc.AVISO_MES_EM_FALTA: "Há meses sem registo antes deste: o ganho cobre vários meses.",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    conn = db.connect()
    db.init_db(conn)  # idempotente: cria as tabelas só se faltarem
    conn.close()
    yield


app = FastAPI(title="Personal Wealth Manager", lifespan=lifespan)

# Só se responde a pedidos para a própria máquina: um domínio externo que passe a apontar para 127.0.0.1
# (DNS rebinding) chega com outro Host e é recusado.
HOSTS_PERMITIDOS = {"127.0.0.1", "localhost"}


@app.middleware("http")
async def so_pedidos_locais(request: Request, call_next):
    """Recusa Hosts alheios e POSTs vindos de outra origem (CSRF: outro site a submeter formulários aqui).

    Um POST sem Origin nem Referer (curl, testes) passa: os browsers mandam sempre Origin num POST.
    """
    host = request.headers.get("host", "")
    if (urlsplit(f"//{host}").hostname or "") not in HOSTS_PERMITIDOS:
        return PlainTextResponse("Host não permitido", status_code=400)
    if request.method == "POST":
        origem = request.headers.get("origin") or request.headers.get("referer")
        if origem is not None and urlsplit(origem).netloc != host:
            return PlainTextResponse("Pedido de outra origem recusado", status_code=403)
    return await call_next(request)

# Bibliotecas JS guardadas localmente (a aplicação funciona offline). check_dir=False: sem a pasta, o /static dá 404 em vez de a app não arrancar.
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static"), check_dir=False), name="static")


def _ecra_painel(request: Request, conn, *, despesa_texto=None, erro_despesa=None, msg=None,
                 aviso_backup=None, status_code=200):
    """Painel. `despesa_texto`: o que foi escrito no campo da despesa (para não o perder num erro)."""
    painel = dashboard.construir_painel(conn)
    if despesa_texto is None:
        atual = painel.cobertura.despesa_mensal_cent if painel and painel.cobertura else None
        despesa_texto = checkin.cent_para_texto(atual) if atual is not None else ""
    contexto = {
        "painel": painel,
        "dados": dashboard.dados_graficos(painel) if painel else None,
        "avisos": AVISOS,
        "despesa_texto": despesa_texto,
        "erro_despesa": erro_despesa,
        "msg": msg,
        "aviso_backup": aviso_backup,
    }
    return templates.TemplateResponse(request, "dashboard.html", contexto, status_code=status_code)


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    conn = db.connect()
    try:
        return _ecra_painel(request, conn)
    finally:
        conn.close()


@app.post("/configuracao/despesa-mensal", response_class=HTMLResponse)
async def despesa_mensal_gravar(request: Request):
    """Grava a despesa mensal de referência (em branco = apagar). Responde com o painel."""
    texto = str((await request.form()).get("despesa_mensal", ""))
    conn = db.connect()
    try:
        try:
            cent = configuracao.validar_despesa_mensal(texto)
        except ValueError as exc:
            return _ecra_painel(request, conn, despesa_texto=texto, erro_despesa=str(exc), status_code=422)
        configuracao.definir_despesa_mensal(conn, cent)
        aviso = _backup_depois_de_mudar(conn)
        msg = (f"Despesa mensal de referência: {calc.formatar_euros(cent)}." if cent is not None
               else "Despesa mensal de referência apagada.")
        return _ecra_painel(request, conn, msg=msg, aviso_backup=aviso)
    finally:
        conn.close()


def desligar() -> None:
    """Pede ao uvicorn que termine, como um Ctrl+C. Fica isolada para os testes a substituírem."""
    time.sleep(0.5)  # deixa a resposta chegar ao browser antes de o servidor fechar
    signal.raise_signal(signal.SIGINT)  # os.kill com SIGINT no Windows mataria o processo à bruta


@app.post("/sair", response_class=HTMLResponse)
def sair(request: Request, tarefas: BackgroundTasks):
    """Guarda a cópia de segurança final e só depois fecha. Se a cópia falhar, a app fica aberta."""
    try:
        conn = db.connect()
        try:
            copia = backup.exportar_csv(conn, backup.pasta_backup_por_defeito())
        finally:
            conn.close()
    except Exception as exc:
        contexto = {"erro": f"{type(exc).__name__}: {exc}"}
        return templates.TemplateResponse(request, "sair.html", contexto, status_code=500)
    tarefas.add_task(desligar)
    return templates.TemplateResponse(request, "sair.html", {"copia": copia.name})


def _linhas_indices(conn, mes, textos=None, erros=None) -> list[dict]:
    """Índices ativos no check-in: valor deste mês (gravado ou escrito) e o último anterior como referência."""
    textos, erros = textos or {}, erros or {}
    gravados = indices.valores_do_mes(conn, mes)
    rotulos = categorias.rotulos(conn)
    linhas = []
    for i in indices.listar(conn, so_ativos=True):
        anterior = conn.execute(
            "SELECT mes, valor FROM valores_indice WHERE indice_id = ? AND mes < ? ORDER BY mes DESC LIMIT 1",
            (i.id, mes),
        ).fetchone()
        por_defeito = indices.valor_para_texto(gravados[i.id]) if i.id in gravados else ""
        linhas.append({
            "i": i, "perimetro": rotulos.get(i.perimetro, i.perimetro) if i.perimetro else "Património todo",
            "texto": textos.get(i.id, por_defeito), "erro": erros.get(i.id), "registado": i.id in gravados,
            "anterior": (anterior["mes"], indices.valor_para_texto(anterior["valor"])) if anterior else None,
        })
    return linhas


def _contexto(conn, mes, data_leitura, valores=None, erros=None, resultado=None, erro_geral=None,
              marcados=None, textos_indices=None, erros_indices=None) -> dict:
    """Prepara o ecrã: `valores` são os textos que o utilizador escreveu (para não os perder num erro);
    `marcados`, as caixas do desafio que ele tinha marcadas (plataforma -> datas AAAA-MM-DD);
    `textos_indices` / `erros_indices`, o mesmo para os valores dos índices (v6)."""
    valores = valores or {}
    erros = erros or {}
    marcados = marcados or {}
    linhas = []
    for l in checkin.linhas_checkin(conn, mes, data_leitura):
        por_defeito = (
            checkin.cent_para_texto(l.saldo_cent) if l.saldo_cent is not None else "",
            checkin.cent_para_texto(l.aporte_cent),
        )
        saldo, aporte = valores.get(l.plataforma_id, por_defeito)
        caixas = marcados.get(l.plataforma_id, {d.isoformat() for d in l.domingos_marcados})
        linhas.append({"l": l, "saldo": saldo, "aporte": aporte, "erro": erros.get(l.plataforma_id),
                       "marcados": caixas})
    return {
        "mes": mes,
        "data_leitura": data_leitura.isoformat(),
        "linhas": linhas,
        "resultado": resultado,
        "avisos": AVISOS,
        "erro_geral": erro_geral,
        "por_gravar": bool(erros or erros_indices),  # voltou de um erro: os valores no ecrã não estão gravados
        "linhas_indices": _linhas_indices(conn, mes, textos_indices, erros_indices),
    }


def _data_do_formulario(texto: str | None, mes: str) -> date:
    """Data da leitura escrita pelo utilizador; em branco = a de defeito do mês. Levanta ValueError se inválida."""
    texto = (texto or "").strip()
    if not texto:
        return checkin.data_por_defeito(mes)
    try:
        data = date.fromisoformat(texto)
    except ValueError:
        raise ValueError(f"Data da leitura inválida: {texto!r} (esperado AAAA-MM-DD)") from None
    checkin.validar_data_leitura(data, mes)
    return data


def _data_para_ver(conn, texto: str | None, mes: str) -> date:
    """Data a mostrar no ecrã. Sem data escolhida: a já gravada nesse mês, ou a de defeito.

    Uma data que não serve para o mês (ex.: depois de mudar de mês) volta à de defeito. Na gravação a
    validação é estrita; aqui o campo mostra sempre a data que vai ser usada.
    """
    if not (texto or "").strip():
        gravada = checkin.data_gravada(conn, mes)
        if gravada is not None:
            return gravada
    try:
        return _data_do_formulario(texto, mes)
    except ValueError:
        return checkin.data_por_defeito(mes)


@app.get("/checkin", response_class=HTMLResponse)
def checkin_ver(request: Request, mes: str | None = None, data: str | None = None):
    atual = checkin.mes_de(date.today())
    mes = (mes or atual).strip()
    erro_geral = None
    try:
        checkin.validar_mes(mes)
    except ValueError as exc:
        erro_geral, mes = str(exc), atual
    conn = db.connect()
    try:
        data_leitura = _data_para_ver(conn, data, mes)
        contexto = _contexto(conn, mes, data_leitura, erro_geral=erro_geral)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "checkin.html", contexto, status_code=400 if erro_geral else 200)


@app.post("/checkin", response_class=HTMLResponse)
async def checkin_gravar(request: Request):
    form = await request.form()
    mes = str(form.get("mes", "")).strip()

    entradas: list[checkin.Entrada] = []
    valores: dict[int, tuple[str, str]] = {}
    marcados: dict[int, set[str]] = {}
    for chave, valor in form.items():
        if not chave.startswith("saldo_"):
            continue
        try:
            pid = int(chave[len("saldo_"):])
        except ValueError:
            continue
        aporte = str(form.get(f"aporte_{pid}", ""))
        # A linha traz caixas do desafio (marcador escondido): as não marcadas não chegam no formulário.
        domingos = tuple(str(d) for d in form.getlist(f"domingo_{pid}")) if form.get(f"desafio_{pid}") else None
        entradas.append(checkin.Entrada(pid, str(valor), aporte, domingos))
        valores[pid] = (str(valor), aporte)
        if domingos is not None:
            marcados[pid] = set(domingos)
    textos_indices: dict[int, str] = {}
    for chave, valor in form.items():
        if chave.startswith("indice_"):
            try:
                textos_indices[int(chave[len("indice_"):])] = str(valor)
            except ValueError:
                continue

    conn = db.connect()
    try:
        try:
            data = _data_do_formulario(str(form.get("data", "")), mes)
            resultado = checkin.gravar_checkin(conn, mes, entradas, date.today(), data_leitura=data,
                                               valores_indices=textos_indices)
        except ValueError as exc:  # mês ou data inválidos ou futuros
            mes_atual = checkin.mes_de(date.today())
            contexto = _contexto(conn, mes_atual, checkin.data_por_defeito(mes_atual), erro_geral=str(exc))
            return templates.TemplateResponse(request, "checkin.html", contexto, status_code=400)
        if not resultado.ok:
            contexto = _contexto(
                conn, mes, data, valores=valores, erros=resultado.erros, marcados=marcados,
                textos_indices=textos_indices, erros_indices=resultado.erros_indices,
                erro_geral="Nada foi gravado: corrige as linhas assinaladas.",
            )
            return templates.TemplateResponse(request, "checkin.html", contexto, status_code=422)
        contexto = _contexto(conn, mes, data, resultado=resultado)
        try:  # os dados já estão gravados: uma cópia falhada avisa, não desfaz
            backup.exportar_csv(conn, backup.pasta_backup_por_defeito())
        except Exception as exc:
            contexto["aviso_backup"] = (
                f"Gravado, mas a cópia de segurança falhou ({type(exc).__name__}: {exc}). "
                "Carrega em Guardar e sair para tentar outra vez."
            )
    finally:
        conn.close()
    return templates.TemplateResponse(request, "checkin.html", contexto)


# --- Plataformas -------------------------------------------------------------

def _backup_depois_de_mudar(conn) -> str | None:
    """Cópia de segurança depois de uma alteração; se falhar, devolve o aviso (a alteração fica)."""
    try:
        backup.exportar_csv(conn, backup.pasta_backup_por_defeito())
    except Exception as exc:
        return f"Gravado, mas a cópia de segurança falhou ({type(exc).__name__}: {exc}). Carrega em Guardar e sair para tentar outra vez."
    return None


def _ecra_plataformas(request: Request, conn, *, editar=None, form=None, erros=None, msg=None, erro_geral=None,
                      aviso_backup=None, status_code=200, erros_categorias=None, nomes_categorias=None,
                      msg_categorias=None, saltar_para=None):
    """Lista de plataformas + formulário (novo ou edição de `editar`) + categorias. `form`: textos já escritos.

    `erros_categorias` / `nomes_categorias`: por código (ou "nova"), o erro e o nome escrito numa categoria.
    `saltar_para`: id da secção para onde a página desce ao abrir (o endereço de um POST não leva âncora).
    """
    if form is None:
        if editar is not None:
            form = {
                "nome": editar["nome"], "categoria": editar["categoria"], "titular": editar["titular"],
                "finalidade": editar["finalidade"] or "", "plano_mensal": checkin.cent_para_texto(editar["plano_mensal_cent"]),
                "calcula_ganho": "1" if editar["calcula_ganho"] else "", "entra_alocacao": "1" if editar["entra_alocacao"] else "",
                "posicao": plataformas.posicao_atual(conn, editar["id"]), "desafio": "1" if editar["desafio_inicio"] else "",
                "desafio_inicio": editar["desafio_inicio"] or "",
            }
        else:
            form = {"calcula_ganho": "1", "entra_alocacao": "1", "posicao": plataformas.POSICAO_FIM,
                    "plano_mensal": "0,00", "desafio_inicio": f"{date.today().year}-01-01"}
    lista_categorias = categorias.listar(conn)
    if saltar_para is None and erros:
        saltar_para = "formulario"
    contexto = {
        "lista": plataformas.listar(conn), "editar": editar, "form": form, "erros": erros or {},
        "msg": msg, "erro_geral": erro_geral, "aviso_backup": aviso_backup,
        "categorias": lista_categorias, "opcoes_posicao": plataformas.opcoes_posicao(conn), "rotulos": {c.codigo: c.nome for c in lista_categorias},
        "erros_categorias": erros_categorias or {}, "nomes_categorias": nomes_categorias or {},
        "msg_categorias": msg_categorias, "saltar_para": saltar_para,
        "ultimo": plataformas.ultimo_saldo(conn, editar["id"]) if editar is not None else None,
    }
    return templates.TemplateResponse(request, "plataformas.html", contexto, status_code=status_code)


def _campo_do_erro(exc: ValueError) -> str:
    """Campo do formulário onde mostrar um erro de gravação: posição escolhida ou nome repetido."""
    return "posicao" if isinstance(exc, plataformas.PosicaoInvalida) else "nome"


def _form_texto(form) -> dict[str, str]:
    return {k: str(v) for k, v in form.items()}


@app.get("/plataformas", response_class=HTMLResponse)
def plataformas_ver(request: Request):
    conn = db.connect()
    try:
        return _ecra_plataformas(request, conn)
    finally:
        conn.close()


@app.post("/plataformas", response_class=HTMLResponse)
async def plataformas_criar(request: Request):
    form = _form_texto(await request.form())
    conn = db.connect()
    try:
        v = plataformas.validar(form, categorias.codigos(conn))
        if not v.ok:
            return _ecra_plataformas(request, conn, form=form, erros=v.erros,
                                     erro_geral="Nada foi gravado: corrige os campos assinalados.", status_code=422)
        try:
            plataformas.criar(conn, v.dados)
        except ValueError as exc:
            return _ecra_plataformas(request, conn, form=form, erros={_campo_do_erro(exc): str(exc)},
                                     erro_geral="Nada foi gravado.", status_code=422)
        aviso = _backup_depois_de_mudar(conn)
        return _ecra_plataformas(request, conn, msg=f"Plataforma {v.dados.nome!r} criada.", aviso_backup=aviso)
    finally:
        conn.close()


def _obter_ou_404(request: Request, conn, plataforma_id: int):
    p = plataformas.obter(conn, plataforma_id)
    if p is None:
        return None, _ecra_plataformas(request, conn, erro_geral="Plataforma inexistente.", status_code=404)
    return p, None


@app.get("/plataformas/{plataforma_id}", response_class=HTMLResponse)
def plataforma_ver(request: Request, plataforma_id: int):
    conn = db.connect()
    try:
        p, erro = _obter_ou_404(request, conn, plataforma_id)
        return erro or _ecra_plataformas(request, conn, editar=p)
    finally:
        conn.close()


@app.post("/plataformas/{plataforma_id}", response_class=HTMLResponse)
async def plataforma_atualizar(request: Request, plataforma_id: int):
    form = _form_texto(await request.form())
    conn = db.connect()
    try:
        p, erro = _obter_ou_404(request, conn, plataforma_id)
        if erro:
            return erro
        v = plataformas.validar(form, categorias.codigos(conn))
        if not v.ok:
            return _ecra_plataformas(request, conn, editar=p, form=form, erros=v.erros,
                                     erro_geral="Nada foi gravado: corrige os campos assinalados.", status_code=422)
        try:
            plataformas.atualizar(conn, plataforma_id, v.dados)
        except ValueError as exc:
            return _ecra_plataformas(request, conn, editar=p, form=form, erros={_campo_do_erro(exc): str(exc)},
                                     erro_geral="Nada foi gravado.", status_code=422)
        aviso = _backup_depois_de_mudar(conn)
        return _ecra_plataformas(request, conn, msg=f"Plataforma {v.dados.nome!r} atualizada.", aviso_backup=aviso)
    finally:
        conn.close()


@app.post("/plataformas/{plataforma_id}/{acao}", response_class=HTMLResponse)
def plataforma_acao(request: Request, plataforma_id: int, acao: str):
    conn = db.connect()
    try:
        p, erro = _obter_ou_404(request, conn, plataforma_id)
        if erro:
            return erro
        try:
            if acao == "desativar":
                plataformas.desativar(conn, plataforma_id)
                msg = f"{p['nome']} desativada: sai do check-in e dos cartões; o histórico fica no painel."
            elif acao == "reativar":
                plataformas.reativar(conn, plataforma_id)
                msg = f"{p['nome']} reativada: volta a aparecer no check-in."
            elif acao == "apagar":
                plataformas.apagar(conn, plataforma_id)
                msg = f"{p['nome']} apagada."
            else:
                return _ecra_plataformas(request, conn, erro_geral="Ação desconhecida.", status_code=404)
        except (ValueError, LookupError) as exc:
            return _ecra_plataformas(request, conn, editar=p, erro_geral=str(exc), status_code=422)
        aviso = _backup_depois_de_mudar(conn)
        return _ecra_plataformas(request, conn, msg=msg, aviso_backup=aviso)
    finally:
        conn.close()


# --- Categorias (esquema v5): criam-se, renomeiam-se e apagam-se no ecrã das plataformas --------------------

def _depois_de_categoria(request: Request, conn, msg: str):
    aviso = _backup_depois_de_mudar(conn)
    return _ecra_plataformas(request, conn, msg_categorias=msg, aviso_backup=aviso, saltar_para="categorias")


def _erro_categoria(request: Request, conn, chave: str, nome: str, erro: str, status_code: int = 422):
    return _ecra_plataformas(request, conn, erros_categorias={chave: erro}, nomes_categorias={chave: nome},
                             saltar_para="categorias", status_code=status_code)


@app.post("/categorias", response_class=HTMLResponse)
async def categoria_criar(request: Request):
    nome = str((await request.form()).get("nome") or "")
    conn = db.connect()
    try:
        try:
            categorias.criar(conn, nome)
        except ValueError as exc:
            return _erro_categoria(request, conn, "nova", nome, str(exc))
        return _depois_de_categoria(request, conn, f"Categoria {' '.join(nome.split())!r} criada: já a podes escolher nas plataformas.")
    finally:
        conn.close()


@app.post("/categorias/{codigo}", response_class=HTMLResponse)
async def categoria_renomear(request: Request, codigo: str):
    nome = str((await request.form()).get("nome") or "")
    conn = db.connect()
    try:
        try:
            categorias.renomear(conn, codigo, nome)
        except LookupError as exc:
            return _ecra_plataformas(request, conn, erro_geral=f"{exc}.", status_code=404)
        except ValueError as exc:
            return _erro_categoria(request, conn, codigo, nome, str(exc))
        return _depois_de_categoria(request, conn, f"Categoria renomeada para {' '.join(nome.split())!r}.")
    finally:
        conn.close()


@app.post("/categorias/{codigo}/apagar", response_class=HTMLResponse)
def categoria_apagar(request: Request, codigo: str):
    conn = db.connect()
    try:
        nome = categorias.rotulos(conn).get(codigo, codigo)
        try:
            categorias.apagar(conn, codigo)
        except LookupError as exc:
            return _ecra_plataformas(request, conn, erro_geral=f"{exc}.", status_code=404)
        except ValueError as exc:
            return _erro_categoria(request, conn, codigo, nome, str(exc))
        return _depois_de_categoria(request, conn, f"Categoria {nome!r} apagada.")
    finally:
        conn.close()


# --- Índices de referência (esquema v6) ----------------------------------------------------------------------

def _ecra_indices(request: Request, conn, *, editar=None, form=None, erro=None, msg=None, erro_geral=None,
                  aviso_backup=None, status_code=200):
    """Lista de índices, formulário (novo ou edição de `editar`) e valores gravados. `form`: textos já escritos."""
    if form is None:
        form = {"nome": editar.nome, "perimetro": editar.perimetro or ""} if editar else {"nome": "", "perimetro": ""}
    lista = indices.listar(conn)
    contexto = {
        "lista": lista, "editar": editar, "form": form, "erro": erro, "msg": msg, "erro_geral": erro_geral,
        "aviso_backup": aviso_backup, "categorias": categorias.listar(conn), "rotulos": categorias.rotulos(conn),
        "valores": {
            i.id: [(m, indices.valor_para_texto(v)) for m, v in reversed(indices.valores(conn, i.id).items())]
            for i in lista
        },
    }
    return templates.TemplateResponse(request, "indices.html", contexto, status_code=status_code)


def _indice_ou_404(request: Request, conn, indice_id: int):
    i = indices.obter(conn, indice_id)
    if i is None:
        return None, _ecra_indices(request, conn, erro_geral="Índice inexistente.", status_code=404)
    return i, None


@app.get("/indices", response_class=HTMLResponse)
def indices_ver(request: Request):
    conn = db.connect()
    try:
        return _ecra_indices(request, conn)
    finally:
        conn.close()


@app.post("/indices", response_class=HTMLResponse)
async def indice_criar(request: Request):
    form = _form_texto(await request.form())
    conn = db.connect()
    try:
        try:
            indices.criar(conn, form.get("nome", ""), form.get("perimetro"))
        except ValueError as exc:
            return _ecra_indices(request, conn, form=form, erro=str(exc), status_code=422)
        aviso = _backup_depois_de_mudar(conn)
        nome = " ".join(form.get("nome", "").split())
        return _ecra_indices(request, conn, msg=f"Índice {nome!r} criado: o valor escreve-se no check-in.",
                             aviso_backup=aviso)
    finally:
        conn.close()


@app.get("/indices/{indice_id}", response_class=HTMLResponse)
def indice_ver(request: Request, indice_id: int):
    conn = db.connect()
    try:
        i, erro = _indice_ou_404(request, conn, indice_id)
        return erro or _ecra_indices(request, conn, editar=i)
    finally:
        conn.close()


@app.post("/indices/{indice_id}", response_class=HTMLResponse)
async def indice_editar(request: Request, indice_id: int):
    form = _form_texto(await request.form())
    conn = db.connect()
    try:
        i, erro = _indice_ou_404(request, conn, indice_id)
        if erro:
            return erro
        try:
            indices.editar(conn, indice_id, form.get("nome", ""), form.get("perimetro"))
        except ValueError as exc:
            return _ecra_indices(request, conn, editar=i, form=form, erro=str(exc), status_code=422)
        aviso = _backup_depois_de_mudar(conn)
        return _ecra_indices(request, conn, msg="Índice atualizado.", aviso_backup=aviso)
    finally:
        conn.close()


@app.post("/indices/{indice_id}/valores/{mes}/apagar", response_class=HTMLResponse)
def indice_apagar_valor(request: Request, indice_id: int, mes: str):
    conn = db.connect()
    try:
        i, erro = _indice_ou_404(request, conn, indice_id)
        if erro:
            return erro
        try:
            indices.apagar_valor(conn, indice_id, mes)
        except LookupError as exc:
            return _ecra_indices(request, conn, erro_geral=f"{exc}.", status_code=404)
        aviso = _backup_depois_de_mudar(conn)
        return _ecra_indices(request, conn, msg=f"Valor de {calc.formatar_mes(mes)} apagado em {i.nome}.",
                             aviso_backup=aviso)
    finally:
        conn.close()


@app.post("/indices/{indice_id}/{acao}", response_class=HTMLResponse)
def indice_acao(request: Request, indice_id: int, acao: str):
    conn = db.connect()
    try:
        i, erro = _indice_ou_404(request, conn, indice_id)
        if erro:
            return erro
        try:
            if acao == "desativar":
                indices.definir_ativo(conn, indice_id, False)
                msg = f"{i.nome} desativado: sai do check-in e do painel; os valores ficam guardados."
            elif acao == "reativar":
                indices.definir_ativo(conn, indice_id, True)
                msg = f"{i.nome} reativado."
            elif acao == "apagar":
                indices.apagar(conn, indice_id)
                msg = f"{i.nome} apagado."
            else:
                return _ecra_indices(request, conn, erro_geral="Ação desconhecida.", status_code=404)
        except (ValueError, LookupError) as exc:
            return _ecra_indices(request, conn, erro_geral=str(exc), status_code=422)
        aviso = _backup_depois_de_mudar(conn)
        return _ecra_indices(request, conn, msg=msg, aviso_backup=aviso)
    finally:
        conn.close()
