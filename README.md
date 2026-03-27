# elimina-spazi

Script Python che legge i file XML da `in/`, corregge le occorrenze errate nei tag `<causale>` che contengono `/PUR/` e salva i file elaborati in `out/`.

## Uso

```bash
python3 fix_causale_pur.py
```

Percorsi personalizzati:

```bash
python3 fix_causale_pur.py /percorso/in --output-dir /percorso/out
```

## Struttura

- `fix_causale_pur.py`: script principale
- `in/`: cartella input tracciata nel repository
- `out/`: cartella output tracciata nel repository

