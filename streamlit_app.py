"""
PriceBot — панель наценок (Streamlit Community Cloud).

Код панели лежит в публичном репо. Настройки и статус — в приватном репо
PriceBot (settings.json, state.json), доступ через GitHub API по токену
из secrets Streamlit. В этом репо нет ни цен, ни настроек, ни секретов.

Secrets (Streamlit → App settings → Secrets):
    PANEL_PASSWORD = "..."          # пароль входа в панель
    GITHUB_TOKEN   = "github_pat_..." # fine-grained, только skorya/skorya-avto-price:
                                     #   Contents: Read and write, Actions: Read and write
    REPO           = "skorya/skorya-avto-price"   # необязательно
"""
import base64
import hmac
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

KYIV = ZoneInfo("Europe/Kyiv")
WORKFLOW = "pricebot.yml"
BRANCH = "main"
WINDOW_TEXT = "7:30 — 14:30 каждые 30 мин"

st.set_page_config(page_title="PriceBot", page_icon="✦", layout="centered",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root {
    --bg:#F7F4EF; --surface:#FFFFFF; --border:#E8E2D9; --text:#1A1714; --muted:#8C8278;
    --accent:#C4975A; --accent2:#2D4A3E; --success:#4A8C6F; --danger:#C4614A;
    --radius:16px; --shadow:0 2px 20px rgba(26,23,20,0.06);
}
html, body, [data-testid="stAppViewContainer"] { background: var(--bg) !important; }
[data-testid="stHeader"], footer, #MainMenu, .stDeployButton { display:none !important; }
.main .block-container { max-width: 780px; }
.hero { text-align:center; margin-bottom:1.5rem; }
.hero h1 { font-size:2.4rem; font-weight:500; color:var(--text); margin:0 0 .3rem; }
.hero p { color:var(--muted); font-size:.88rem; margin:0; }
.status-bar { display:flex; align-items:center; gap:.5rem; background:var(--surface);
    border:1px solid var(--border); border-radius:100px; padding:.55rem 1.2rem;
    margin:0 auto 1rem; width:fit-content; font-size:.82rem; color:var(--muted); box-shadow:var(--shadow); }
.status-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.scard { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
    padding:1.2rem 1.5rem; margin:1rem 0 .5rem; box-shadow:var(--shadow); }
.scard-head { display:flex; align-items:center; justify-content:space-between; gap:.5rem; flex-wrap:wrap; }
.scard-name { font-size:1.3rem; font-weight:500; color:var(--text); }
.scard-sub { font-size:.76rem; color:var(--muted); margin-top:.1rem; }
.badge { font-size:.72rem; font-weight:500; padding:.22rem .65rem; border-radius:100px; white-space:nowrap; }
.badge-on { background:#EBF5EE; color:#4A8C6F; } .badge-off { background:#F5F0EB; color:#8C8278; }
.badge-ok { background:#EBF5EE; color:#4A8C6F; } .badge-error { background:#FAEAE7; color:#C4614A; }
.badge-pending { background:#FDF5EB; color:#C4975A; }
.drive-ok { background:#F0F7F4; border:1px solid #D0E8DC; border-radius:8px; padding:.6rem .9rem;
    font-size:.75rem; color:var(--accent2); word-break:break-all; margin-top:.4rem; }
</style>
""", unsafe_allow_html=True)


# ── Вход по паролю ────────────────────────────────────────────────────────────

def password_ok() -> bool:
    if st.session_state.get("auth_ok"):
        return True
    expected = st.secrets.get("PANEL_PASSWORD", "")
    if not expected:
        st.error("В secrets не задан PANEL_PASSWORD — вход закрыт.")
        return False

    def check():
        entered = st.session_state.get("pwd", "")
        if hmac.compare_digest(entered.encode(), str(expected).encode()):
            st.session_state["auth_ok"] = True
            st.session_state["auth_fail"] = False
        else:
            time.sleep(2)  # замедляет подбор
            st.session_state["auth_fail"] = True
        st.session_state.pop("pwd", None)

    st.markdown('<div class="hero"><h1>✦ PriceBot</h1></div>', unsafe_allow_html=True)
    st.text_input("Пароль", type="password", key="pwd", on_change=check)
    if st.session_state.get("auth_fail"):
        st.error("Неверный пароль")
    return False


if not password_ok():
    st.stop()


# ── GitHub API ────────────────────────────────────────────────────────────────

REPO = st.secrets.get("REPO", "skorya/skorya-avto-price")
API = st.secrets.get("GITHUB_API", "https://api.github.com").rstrip("/")
TOKEN = st.secrets.get("GITHUB_TOKEN", "")
if not TOKEN:
    st.error("В secrets не задан GITHUB_TOKEN.")
    st.stop()


class GitHubError(Exception):
    pass


def gh(method: str, path: str, **kw) -> requests.Response:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        return requests.request(method, f"{API}{path}", headers=headers, timeout=20, **kw)
    except requests.RequestException as e:
        raise GitHubError(f"Нет связи с GitHub: {e.__class__.__name__}") from None


def explain(r: requests.Response) -> str:
    if r.status_code == 401:
        return "GitHub: токен недействителен или истёк (401). Нужен новый GITHUB_TOKEN в secrets."
    if r.status_code in (403, 404):
        return (f"GitHub: нет доступа ({r.status_code}). Проверьте, что токен выдан на {REPO} "
                "с правами Contents и Actions: Read and write.")
    return f"GitHub: ошибка {r.status_code}"


def read_json(path: str) -> tuple[dict, str]:
    r = gh("GET", f"/repos/{REPO}/contents/{path}", params={"ref": BRANCH})
    if r.status_code != 200:
        raise GitHubError(explain(r))
    body = r.json()
    data = json.loads(base64.b64decode(body["content"]).decode("utf-8"))
    return data, body["sha"]


def write_settings(cfg: dict, sha: str) -> str:
    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    stamp = datetime.now(KYIV).strftime("%d.%m.%Y %H:%M")
    r = gh("PUT", f"/repos/{REPO}/contents/settings.json", json={
        "message": f"settings: панель {stamp}",
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": BRANCH,
    })
    if r.status_code in (409, 422):
        raise GitHubError("Настройки кто-то изменил с момента открытия панели. "
                          "Нажмите «Перечитать настройки» и внесите правки заново.")
    if r.status_code not in (200, 201):
        raise GitHubError(explain(r))
    return r.json()["content"]["sha"]


def dispatch_force() -> None:
    r = gh("POST", f"/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
           json={"ref": BRANCH, "inputs": {"force": "true"}})
    if r.status_code != 204:
        raise GitHubError(explain(r))


@st.cache_data(ttl=15, show_spinner=False)
def load_runs() -> list[dict]:
    r = gh("GET", f"/repos/{REPO}/actions/workflows/{WORKFLOW}/runs", params={"per_page": 10})
    if r.status_code != 200:
        raise GitHubError(explain(r))
    return r.json().get("workflow_runs", [])


@st.cache_data(ttl=30, show_spinner=False)
def load_state() -> dict:
    data, _ = read_json("state.json")
    return data


def kyiv_time(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KYIV)
        return t.strftime("%d.%m.%Y %H:%M")
    except (ValueError, AttributeError):
        return iso or "—"


# ── Наценка: та же логика, что apply_markup в worker.py ───────────────────────

def parse_rules(rules_str: str) -> tuple[list[tuple[float, float, float]], list[str]]:
    rules, errors = [], []
    for idx, rule in enumerate((rules_str or "").split(";")):
        rule = rule.strip()
        if not rule:
            continue
        if "=" not in rule or "-" not in rule:
            errors.append(f"правило {idx + 1} «{rule}»: нужен вид ОТ-ДО=%")
            continue
        try:
            range_part, pct = rule.split("=", 1)
            lo, hi = map(float, range_part.split("-", 1))
            pct = float(pct)
        except ValueError:
            errors.append(f"правило {idx + 1} «{rule}»: не число")
            continue
        if lo >= hi:
            errors.append(f"правило {idx + 1} «{rule}»: ОТ должно быть меньше ДО")
            continue
        rules.append((lo, hi, pct))
    return rules, errors


def apply_markup(price: float, base_markup: float, rules_str: str) -> int:
    markup = base_markup
    for lo, hi, pct in parse_rules(rules_str)[0]:
        if lo <= price < hi:
            markup = pct
            break
    return int(round(price * (1 + markup / 100)))


# ── Загрузка настроек (один раз за сессию, «Перечитать» — заново) ─────────────

def load_settings_into_session() -> None:
    cfg, sha = read_json("settings.json")
    st.session_state["cfg"] = cfg
    st.session_state["sha"] = sha
    for k in [k for k in st.session_state if k.startswith("w_")]:
        del st.session_state[k]


try:
    if "cfg" not in st.session_state:
        load_settings_into_session()
except GitHubError as e:
    st.error(str(e))
    st.stop()

cfg: dict = st.session_state["cfg"]


# ── Шапка и статус робота (обновляется сам каждые 20 с) ───────────────────────

st.markdown(f"""
<div class="hero"><h1>✦ PriceBot</h1>
<p>Автоматическое обновление прайсов &nbsp;·&nbsp; {WINDOW_TEXT}</p></div>
""", unsafe_allow_html=True)


@st.fragment(run_every="20s")
def status_block() -> None:
    try:
        runs = load_runs()
    except GitHubError as e:
        st.warning(str(e))
        return
    active = [r for r in runs if r.get("status") in ("queued", "in_progress", "waiting", "pending")]
    done = [r for r in runs if r.get("status") == "completed"]
    st.session_state["robot_busy"] = bool(active)

    if active:
        color, text = "var(--accent)", "🔄 Робот работает прямо сейчас…"
    elif done:
        last = done[0]
        ok = last.get("conclusion") == "success"
        color = "var(--success)" if ok else "var(--danger)"
        mark = "✓" if ok else "✗ ошибка"
        text = f"Последний запуск робота: <strong>{kyiv_time(last.get('created_at', ''))}</strong> {mark}"
    else:
        color, text = "var(--accent)", "Запусков ещё не было"
    st.markdown(f'<div class="status-bar"><div class="status-dot" style="background:{color}"></div>'
                f'{text}</div>', unsafe_allow_html=True)

    if done and done[0].get("conclusion") not in ("success", None):
        st.error(f"Последний запуск завершился с ошибкой. Подробности: {done[0].get('html_url', '')}")


status_block()

try:
    state = load_state()
except GitHubError as e:
    state = {}
    st.warning(str(e))


# ── Карточки поставщиков ──────────────────────────────────────────────────────

all_errors: list[str] = []

for key, sup in cfg.get("suppliers", {}).items():
    sup_state = state.get(key, {})
    if not sup_state:
        status_badge = '<span class="badge badge-pending">● Ожидание</span>'
    elif sup_state.get("ok"):
        status_badge = f'<span class="badge badge-ok">✓ {sup_state.get("message", "")}</span>'
    else:
        status_badge = f'<span class="badge badge-error">✗ {sup_state.get("message", "Ошибка")}</span>'
    enabled_badge = ('<span class="badge badge-on">● Активен</span>' if sup.get("enabled", True)
                     else '<span class="badge badge-off">○ Выкл</span>')
    updated = sup_state.get("updated_at", "")
    sub = f"📧 {sup.get('email_sender', '')}" + (f" &nbsp;·&nbsp; прайс обновлён: {updated}" if updated else "")

    st.markdown(f"""
    <div class="scard"><div class="scard-head">
      <div><div class="scard-name">{sup.get('name', key)}</div><div class="scard-sub">{sub}</div></div>
      <div style="display:flex;gap:.4rem;align-items:center">{status_badge} {enabled_badge}</div>
    </div></div>
    """, unsafe_allow_html=True)

    with st.expander("⚙️ Настройки", expanded=False):
        st.toggle("Поставщик активен", value=bool(sup.get("enabled", True)), key=f"w_en_{key}")
        c1, c2, c3 = st.columns(3)
        c1.number_input("Наценка %, если цена вне диапазонов", 0, 200,
                        value=int(sup.get("markup", 0)), key=f"w_m_{key}")
        c2.number_input("Мин. остаток", 0, 100, value=int(sup.get("min_stock", 1)), key=f"w_s_{key}")
        c3.number_input("Мин. цена, грн (0 = общая)", 0, 50000,
                        value=int(sup.get("min_price", 0)), step=10, key=f"w_p_{key}")
        st.text_input("Наценка по диапазонам цены закупки",
                      value=sup.get("markup_rules", ""),
                      placeholder="0-500=40; 500-2000=30; 2000-99999=20",
                      help="ОТ-ДО=% через «;». ОТ включительно, ДО — нет. "
                           "Цена вне всех диапазонов — основная наценка.",
                      key=f"w_r_{key}")

        rules_now = st.session_state[f"w_r_{key}"]
        _, errs = parse_rules(rules_now)
        for e in errs:
            st.error(e)
        all_errors += [f"{sup.get('name', key)}: {e}" for e in errs]

        test_price = st.number_input("Проверить: цена закупки, грн", 0, 1_000_000, value=0,
                                     step=100, key=f"t_{key}")
        if test_price:
            out = apply_markup(test_price, st.session_state[f"w_m_{key}"], rules_now)
            st.caption(f"→ цена в прайсе для Автопро: **{out} грн** "
                       f"(+{(out / test_price - 1) * 100:.1f} %)")

        drive_id = sup_state.get("drive_file_id", "")
        if drive_id:
            st.markdown(f'<div class="drive-ok">🔗 https://drive.google.com/uc?export=download&id={drive_id}</div>',
                        unsafe_allow_html=True)
            st.caption("Ссылка для Автопро — постоянная, файл обновляется")

with st.expander("🌍 Общая минимальная цена"):
    st.number_input("Товары дешевле этой цены не попадают ни в один прайс (грн)", 0, 50000,
                    value=int(cfg.get("global", {}).get("min_price", 0)), step=10, key="w_global_min")


def collect_cfg() -> dict:
    new = json.loads(json.dumps(cfg))
    for key, sup in new.get("suppliers", {}).items():
        sup["enabled"] = bool(st.session_state[f"w_en_{key}"])
        sup["markup"] = int(st.session_state[f"w_m_{key}"])
        sup["min_stock"] = int(st.session_state[f"w_s_{key}"])
        sup["min_price"] = int(st.session_state[f"w_p_{key}"])
        sup["markup_rules"] = st.session_state[f"w_r_{key}"].strip()
    new.setdefault("global", {})["min_price"] = int(st.session_state["w_global_min"])
    return new


def save_if_changed() -> bool:
    """True — сохранено или нечего сохранять; False — ошибка (уже показана)."""
    if all_errors:
        st.error("Исправьте ошибки в правилах наценки — настройки не сохранены.")
        return False
    new = collect_cfg()
    if new == cfg:
        return True
    try:
        st.session_state["sha"] = write_settings(new, st.session_state["sha"])
    except GitHubError as e:
        st.error(str(e))
        return False
    st.session_state["cfg"] = new
    return True


# ── Кнопки ────────────────────────────────────────────────────────────────────

st.write("")
col_save, col_run = st.columns(2)

with col_save:
    if st.button("💾  Сохранить", use_container_width=True):
        changed = collect_cfg() != cfg
        if save_if_changed():
            st.success("Настройки сохранены. Применятся при следующем запуске робота."
                       if changed else "Изменений нет.")

with col_run:
    busy = st.session_state.get("robot_busy", False)
    if st.button("⚡  Обновить сейчас", use_container_width=True, type="primary", disabled=busy,
                 help="Сохранить настройки и сразу пересобрать прайсы (вне окна тоже)"):
        if save_if_changed():
            try:
                dispatch_force()
            except GitHubError as e:
                st.error(str(e))
            else:
                load_runs.clear()
                st.success("Робот запущен. Статус вверху обновится в течение минуты; "
                           "сам прогон — около минуты.")

if st.button("↻ Перечитать настройки", help="Отменить несохранённые правки и загрузить настройки заново"):
    try:
        load_settings_into_session()
        load_state.clear()
        load_runs.clear()
    except GitHubError as e:
        st.error(str(e))
    st.rerun()
