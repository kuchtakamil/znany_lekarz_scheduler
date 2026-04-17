# Konfiguracja powiadomień Gmail z Apprise

## Format URL

```
mailto://user:app_pass@gmail.com?to=me@gmail.com
```

## 1. Wygeneruj hasło aplikacji Google

Google nie pozwala używać zwykłego hasła — musisz wygenerować **App Password**:

1. Wejdź na [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Zaloguj się na konto Gmail
3. Wybierz **"Mail"** i **"Other (Custom name)"** → wpisz np. `znany-lekarz`
4. Kliknij **Generate** — dostaniesz 16-znakowy kod (np. `abcd efgh ijkl mnop`)

> Wymaga włączonego 2FA na koncie Google.

## 2. Wstaw do `config.toml`

```toml
[notifications]
urls = [
  "mailto://twoj.email:abcdefghijklmnop@gmail.com?to=odbiorca@gmail.com"
]
```

- `twoj.email` — login Gmail (część przed `@gmail.com`)
- `abcdefghijklmnop` — app password **bez spacji**
- `?to=odbiorca@gmail.com` — adres docelowy (może być ten sam co nadawca)

## Przykład

Jeśli konto to `jan.kowalski@gmail.com`, app password `abcd efgh ijkl mnop`:

```toml
urls = ["mailto://jan.kowalski:abcdefghijklmnop@gmail.com?to=jan.kowalski@gmail.com"]
```

## Test

```bash
python -m znany_lekarz_scheduler.main --test-notify
```