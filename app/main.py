"""Aplicação web do PWM: página de estado e check-in mensal."""
from __future__ import annotations

import signal
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import backup, calc, checkin, dashboard, db

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["eur"] = calc.formatar_euros

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
# Bibliotecas JS guardadas localmente (a aplicação funciona offline). check_dir=False: sem a pasta, o /static dá 404 em vez de a app não arrancar.
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static"), check_dir=False), name="static")


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    conn = db.connect()
    try:
        painel = dashboard.construir_painel(conn)
    finally:
        conn.close()
    contexto = {
        "painel": painel,
        "dados": dashboard.dados_graficos(painel) if painel else None,
        "avisos": AVISOS,
        "rotulos": dashboard.ROTULOS_CATEGORIA,
    }
    return templates.TemplateResponse(request, "dashboard.html", contexto)


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


def _contexto(conn, mes, data_leitura, valores=None, erros=None, resultado=None, erro_geral=None) -> dict:
    """Prepara o ecrã: `valores` são os textos que o utilizador escreveu (para não os perder num erro)."""
    valores = valores or {}
    erros = erros or {}
    linhas = []
    for l in checkin.linhas_checkin(conn, mes, data_leitura):
        por_defeito = (
            checkin.cent_para_texto(l.saldo_cent) if l.saldo_cent is not None else "",
            checkin.cent_para_texto(l.aporte_cent),
        )
        saldo, aporte = valores.get(l.plataforma_id, por_defeito)
        linhas.append({"l": l, "saldo": saldo, "aporte": aporte, "erro": erros.get(l.plataforma_id)})
    return {
        "mes": mes,
        "data_leitura": data_leitura.isoformat(),
        "linhas": linhas,
        "resultado": resultado,
        "avisos": AVISOS,
        "erro_geral": erro_geral,
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


def _data_para_ver(texto: str | None, mes: str) -> date:
    """No ecrã, uma data que não serve para o mês (ex.: depois de mudar de mês) volta à de defeito.

    Na gravação a validação é estrita; aqui o campo mostra sempre a data que vai ser usada.
    """
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
    data_leitura = _data_para_ver(data, mes)
    conn = db.connect()
    try:
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
    for chave, valor in form.items():
        if not chave.startswith("saldo_"):
            continue
        try:
            pid = int(chave[len("saldo_"):])
        except ValueError:
            continue
        aporte = str(form.get(f"aporte_{pid}", ""))
        entradas.append(checkin.Entrada(pid, str(valor), aporte))
        valores[pid] = (str(valor), aporte)

    conn = db.connect()
    try:
        try:
            data = _data_do_formulario(str(form.get("data", "")), mes)
            resultado = checkin.gravar_checkin(conn, mes, entradas, date.today(), data_leitura=data)
        except ValueError as exc:  # mês ou data inválidos ou futuros
            mes_atual = checkin.mes_de(date.today())
            contexto = _contexto(conn, mes_atual, checkin.data_por_defeito(mes_atual), erro_geral=str(exc))
            return templates.TemplateResponse(request, "checkin.html", contexto, status_code=400)
        if not resultado.ok:
            contexto = _contexto(
                conn, mes, data, valores=valores, erros=resultado.erros,
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
