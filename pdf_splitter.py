#!/usr/bin/env python3
"""PDF Splitter — divisor de PDF con interfaz gráfica (se abre en tu navegador, todo es local).

Copia las páginas tal cual (sin recomprimir), así las imágenes no pierden calidad.
Requiere: pip3 install --user pypdf
"""
import json
import logging
import os
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pypdf import PdfReader, PdfWriter

logging.getLogger("pypdf").setLevel(logging.ERROR)  # silencia avisos del PDF

PUERTO = 8765
estado = {"reader": None, "ruta": "", "total": 0, "salida": "",
          "progreso": 0, "max": 0, "mensaje": "", "trabajando": False,
          "resultado": None, "error": None}
candado = threading.Lock()


def nombre_seguro(texto):
    limpio = "".join(c for c in texto if c not in '/\\:*?"<>|').strip()
    return limpio or "parte"


def osascript(script):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip()


def abrir_pdf(ruta):
    reader = PdfReader(ruta)
    if reader.is_encrypted:
        reader.decrypt("")
    estado.update(reader=reader, ruta=ruta, total=len(reader.pages))
    if not estado["salida"]:
        estado["salida"] = os.path.dirname(ruta)


def info():
    r = estado
    return {"ruta": r["ruta"], "nombre": os.path.basename(r["ruta"]), "total": r["total"],
            "mb": round(os.path.getsize(r["ruta"]) / 1048576) if r["ruta"] else 0,
            "salida": r["salida"], "progreso": r["progreso"], "max": r["max"],
            "mensaje": r["mensaje"], "trabajando": r["trabajando"],
            "resultado": r["resultado"], "error": r["error"]}


def dividir(trabajos):
    try:
        reader = estado["reader"]
        hechos = []
        for nombre, desde, hasta, ruta in trabajos:
            estado["mensaje"] = f"Creando «{nombre}» (hojas {desde}-{hasta})…"
            w = PdfWriter()
            for p in range(desde - 1, hasta):
                w.add_page(reader.pages[p])
                estado["progreso"] += 1
            w.compress_identical_objects()  # quita objetos duplicados o sin usar
            with open(ruta, "wb") as f:
                w.write(f)
            hechos.append(f"{os.path.basename(ruta)} — {os.path.getsize(ruta)/1048576:.1f} MB")
        estado["resultado"] = hechos
        estado["mensaje"] = "Listo ✔"
    except Exception as e:
        estado["error"] = str(e)
        estado["mensaje"] = "Ocurrió un error"
    finally:
        estado["trabajando"] = False


def iniciar_division(partes):
    if estado["trabajando"]:
        return "Ya se está dividiendo, espera."
    if not estado["reader"]:
        return "Primero elige el PDF."
    if not partes:
        return "Agrega al menos una parte."
    total, carpeta = estado["total"], estado["salida"]
    trabajos = []
    for p in partes:
        desde, hasta = int(p["desde"]), int(p["hasta"])
        if not (1 <= desde <= hasta <= total):
            return f"«{p['nombre']}»: las hojas deben estar entre 1 y {total}."
        ruta = os.path.join(carpeta, nombre_seguro(p["nombre"]) + ".pdf")
        if os.path.abspath(ruta) == os.path.abspath(estado["ruta"]):
            return f"«{p['nombre']}» sobrescribiría el PDF original."
        trabajos.append((p["nombre"], desde, hasta, ruta))
    estado.update(progreso=0, max=sum(t[2] - t[1] + 1 for t in trabajos),
                  trabajando=True, resultado=None, error=None)
    threading.Thread(target=dividir, args=(trabajos,), daemon=True).start()
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path == "/":
            cuerpo = PAGINA.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
        elif self.path == "/estado":
            self._json(info())
        else:
            self.send_error(404)

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", 0))
        datos = json.loads(self.rfile.read(largo) or b"{}")
        with candado:
            if self.path == "/elegir_pdf":
                ruta = osascript('POSIX path of (choose file with prompt "Elige el PDF" '
                                 'of type {"com.adobe.pdf"} default location '
                                 '(path to downloads folder))')
                if ruta:
                    try:
                        abrir_pdf(ruta)
                    except Exception as e:
                        return self._json({"error": f"No se pudo abrir el PDF: {e}"})
                self._json(info())
            elif self.path == "/elegir_salida":
                d = osascript('POSIX path of (choose folder with prompt "Carpeta de salida")')
                if d:
                    estado["salida"] = d.rstrip("/")
                self._json(info())
            elif self.path == "/existentes":
                nombres = [nombre_seguro(p["nombre"]) + ".pdf" for p in datos["partes"]]
                self._json({"existentes": [n for n in nombres if
                                           os.path.exists(os.path.join(estado["salida"], n))]})
            elif self.path == "/dividir":
                self._json({"error": iniciar_division(datos["partes"])})
            elif self.path == "/abrir_carpeta":
                subprocess.run(["open", estado["salida"]])
                self._json({})
            else:
                self.send_error(404)


PAGINA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>PDF Splitter</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f5f5f7;--card:#fff;--txt:#1d1d1f;--sub:#6e6e73;--line:#d2d2d7;--acc:#0071e3;--accH:#0062c4;--warn:#c9341f}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1e;--card:#2c2c2e;--txt:#f5f5f7;--sub:#a1a1a6;--line:#3a3a3c;--acc:#0a84ff;--accH:#3395ff;--warn:#ff6b5a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:15px -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif}
main{max-width:720px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:26px;margin:0 0 4px}.lead{color:var(--sub);margin:0 0 22px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--sub);margin:0 0 10px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.grow{flex:1;min-width:0;overflow-wrap:anywhere}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--txt);border-radius:8px;padding:7px 14px;cursor:pointer}
button:hover{border-color:var(--acc)}
button.pri{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600;padding:10px 22px;font-size:16px}
button.pri:hover{background:var(--accH)}button:disabled{opacity:.5;cursor:default}
input{font:inherit;border:1px solid var(--line);background:var(--bg);color:var(--txt);border-radius:8px;padding:7px 9px}
input.n{width:72px}input.name{flex:1;min-width:120px}
table{width:100%;border-collapse:collapse;margin-top:12px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line)}
th{font-size:12px;color:var(--sub);font-weight:500}td.c,th.c{text-align:center}
td button{padding:2px 9px;color:var(--warn)}
.vacio{color:var(--sub);padding:12px 0 2px}
.muted{color:var(--sub);font-size:13px}
progress{width:100%;height:10px;accent-color:var(--acc)}
.msg{margin-top:8px;min-height:20px}.err{color:var(--warn)}
ul{margin:8px 0 0;padding-left:20px}
</style></head><body><main>
<h1>✂️ PDF Splitter</h1>
<p class="lead">Separa tu PDF por unidades sin perder calidad en las imágenes.</p>

<section><h2>1. PDF original</h2>
<div class="row"><div class="grow" id="pdf">Ningún archivo seleccionado</div>
<button onclick="elegirPdf()">Elegir PDF…</button></div></section>

<section><h2>2. Partes — de qué hoja a qué hoja</h2>
<div class="row">
<input class="name" id="nombre" placeholder="Nombre (ej. Unidad 1)">
<input class="n" id="desde" type="number" min="1" placeholder="Desde">
<input class="n" id="hasta" type="number" min="1" placeholder="Hasta">
<button onclick="agregar()">Agregar</button></div>
<table><thead><tr><th>Nombre</th><th class="c">Desde</th><th class="c">Hasta</th><th class="c">Hojas</th><th></th></tr></thead>
<tbody id="tabla"></tbody></table>
<div class="vacio" id="vacio">Aún no hay partes. Agrega una arriba.</div>
<div class="row" style="margin-top:12px"><span class="muted">O automático: cada</span>
<input class="n" id="cada" type="number" min="1"><span class="muted">hojas</span>
<button onclick="auto()">Generar</button><span class="grow"></span>
<button onclick="partes=[];pintar()">Limpiar todo</button></div></section>

<section><h2>3. Carpeta donde guardar</h2>
<div class="row"><div class="grow" id="salida">(misma carpeta del PDF)</div>
<button onclick="elegirSalida()">Cambiar…</button></div></section>

<section><progress id="prog" value="0" max="1"></progress>
<div class="msg" id="msg"></div><div id="res"></div>
<div class="row" style="justify-content:center;margin-top:10px">
<button class="pri" id="btn" onclick="dividir()">Dividir PDF</button></div></section>
</main><script>
let partes=[],total=0,salida="";
const $=id=>document.getElementById(id);
async function post(u,d){const r=await fetch(u,{method:"POST",body:JSON.stringify(d||{})});return r.json()}
function ponerInfo(i){if(i.error){alert(i.error);return}
 total=i.total;salida=i.salida;
 if(i.ruta)$("pdf").innerHTML="<b>"+esc(i.nombre)+"</b> <span class='muted'>— "+i.total+" hojas, "+i.mb+" MB</span>";
 if(i.salida)$("salida").textContent=i.salida;
 $("desde").max=$("hasta").max=total||""}
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function elegirPdf(){ponerInfo(await post("/elegir_pdf"))}
async function elegirSalida(){ponerInfo(await post("/elegir_salida"))}
function agregar(){
 if(!total)return alert("Primero elige el PDF.");
 const d=+$("desde").value,h=+$("hasta").value;
 if(!d||!h||d<1||h>total||d>h)return alert("Las hojas deben estar entre 1 y "+total+", y 'Desde' ≤ 'Hasta'.");
 partes.push({nombre:$("nombre").value.trim()||"Unidad "+(partes.length+1),desde:d,hasta:h});
 $("nombre").value="";$("desde").value=Math.min(h+1,total);$("hasta").value="";$("nombre").focus();pintar()}
function auto(){
 if(!total)return alert("Primero elige el PDF.");
 const c=+$("cada").value;if(!c||c<1)return alert("Escribe cuántas hojas por parte.");
 partes=[];for(let i=1,n=1;i<=total;i+=c,n++)partes.push({nombre:"Parte "+n,desde:i,hasta:Math.min(i+c-1,total)});pintar()}
function pintar(){
 $("tabla").innerHTML=partes.map((p,i)=>"<tr><td>"+esc(p.nombre)+"</td><td class=c>"+p.desde+"</td><td class=c>"+p.hasta+
  "</td><td class=c>"+(p.hasta-p.desde+1)+"</td><td class=c><button onclick='partes.splice("+i+",1);pintar()'>✕</button></td></tr>").join("");
 $("vacio").style.display=partes.length?"none":"block"}
async function dividir(){
 if(!total)return alert("Primero elige el PDF.");
 if(!partes.length)return alert("Agrega al menos una parte.");
 const ex=(await post("/existentes",{partes})).existentes;
 if(ex.length&&!confirm("Ya existen y se reemplazarán:\n"+ex.join("\n")+"\n\n¿Continuar?"))return;
 const r=await post("/dividir",{partes});if(r.error)return alert(r.error);
 $("btn").disabled=true;$("res").innerHTML="";seguir()}
async function seguir(){
 const i=await (await fetch("/estado")).json();
 $("prog").max=i.max||1;$("prog").value=i.progreso;$("msg").textContent=i.mensaje;$("msg").className="msg";
 if(i.trabajando)return setTimeout(seguir,300);
 $("btn").disabled=false;
 if(i.error){$("msg").className="msg err";$("msg").textContent="Error: "+i.error}
 else if(i.resultado)$("res").innerHTML="<ul>"+i.resultado.map(x=>"<li>"+esc(x)+"</li>").join("")+
  "</ul><div class=row style='margin-top:10px'><button onclick='post(\"/abrir_carpeta\")'>Abrir carpeta</button></div>"}
["nombre","desde","hasta"].forEach(id=>$(id).addEventListener("keydown",e=>{if(e.key==="Enter")agregar()}));
pintar();fetch("/estado").then(r=>r.json()).then(ponerInfo);
</script></body></html>"""


if __name__ == "__main__":
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler)
    url = f"http://127.0.0.1:{PUERTO}/"
    print(f"PDF Splitter abierto en {url}\nCierra esta ventana (o Ctrl+C) para salir.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
