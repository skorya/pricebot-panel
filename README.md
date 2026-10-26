# PriceBot — панель наценок

Панель для Streamlit Community Cloud. Здесь только код интерфейса: цен, настроек
и секретов в этом репо нет.

- Настройки (`settings.json`) и статус (`state.json`) лежат в приватном репо PriceBot;
  панель читает и пишет их через GitHub API.
- «Сохранить» — коммит `settings.json`; применяется при следующем запуске робота.
- «Обновить сейчас» — сохраняет и запускает робота (GitHub Actions, `force`).

## Secrets (Streamlit → App settings → Secrets)
```toml
PANEL_PASSWORD = "..."
GITHUB_TOKEN   = "github_pat_..."   # fine-grained, только репо PriceBot:
                                   # Contents и Actions — Read and write
```
