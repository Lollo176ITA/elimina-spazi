# elimina-spazi

Script Python che legge file XML, corregge le occorrenze errate nei tag `<causale>` che contengono `/PUR/` e salva i file elaborati in una cartella di output. Accetta automaticamente sia file `.xml` sia `.XML`.

## Uso

```bash
python3 fix_causale_pur.py
```

Config personalizzato:

```bash
python3 fix_causale_pur.py --config /percorso/config.json
```

Override rapido delle cartelle:

```bash
python3 fix_causale_pur.py /percorso/in --output-dir /percorso/out
```

## Configurazione

Il file `config.json` gestisce i parametri principali:

- `input_dir`: cartella input
- `output_dir`: cartella output
- `recursive`: scansione ricorsiva
- `copy_unmodified_xml`: copia anche gli XML senza modifiche
- `clear_output_before_run`: svuota `output_dir` prima di eseguire
- `zip_output`: crea anche un archivio ZIP dell'output
- `zip_file_name`: nome del file ZIP
- `delete_input_after_success`: cancella la cartella input se tutto termina senza errori XML
- `continue_on_xml_error`: continua anche se un XML non e` valido
- `print_each_change`: stampa il dettaglio di ogni correzione
- `summary_file`: file JSON di riepilogo esecuzione

## Struttura

- `fix_causale_pur.py`: script principale
- `config.json`: configurazione esecuzione
- `in/`: cartella input
- `out/`: cartella output
