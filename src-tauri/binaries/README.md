# Sidecar-binärer

Tauri spawnar Python-backend:en från denna mapp som en sidecar. Bygg den
plattformsberoende med PyInstaller:

```bash
cd ../../backend
pyinstaller --onefile --name hembudget-backend -p hembudget hembudget/main.py
```

Lägg resultatet (med plattforms-suffix) här som:

- `hembudget-backend-x86_64-apple-darwin`
- `hembudget-backend-aarch64-apple-darwin`
- `hembudget-backend-x86_64-pc-windows-msvc.exe`
- `hembudget-backend-x86_64-unknown-linux-gnu`

Tauri väljer rätt binär baserat på byggtargeten. Under `npm run tauri dev`
kan du bygga en en-gångs `hembudget-backend` utan suffix.
