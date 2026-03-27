# elimina-spazi build

Questa branch viene generata automaticamente da GitHub Actions a partire da `main`.
Ogni nuova build riuscita sovrascrive il contenuto della branch `build`.

## Contenuto

- `elimina-spazi.exe`: eseguibile Windows generato con PyInstaller
- `config.json`: configurazione di base
- `build-info.json`: informazioni sulla build e sul commit sorgente
- `SHA256SUMS.txt`: hash SHA-256 dell'eseguibile

## Uso

1. Scarica i file dalla branch `build`.
2. Modifica `config.json` secondo le tue cartelle di lavoro.
3. Prepara la cartella di input con i file XML.
4. Esegui `elimina-spazi.exe`.

## Note

- Lo script accetta sia file `.xml` sia `.XML`.
- Se `zip_output` e` attivo nel `config.json`, il programma crea anche uno ZIP dell'output.
- Se `delete_input_after_success` e` attivo, la cartella di input viene cancellata solo se l'elaborazione termina senza errori XML.
