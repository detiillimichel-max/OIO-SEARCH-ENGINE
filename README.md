# OIO-SEARCH-ENGINE

Motor independente de descoberta e pesquisa para os projetos OIO.

## Módulo 1 — Descobridor de instâncias SearXNG

O workflow consulta a lista pública mantida pelo projeto searx.space, testa instâncias HTTPS e verifica se aceitam pesquisa em JSON.

Relatório: `data/searxng-instances.json`.

O teste inicial encontrou 83 endereços HTTPS e 0 respostas JSON válidas no ambiente do GitHub Actions. Isso não prova que todas estejam offline: JSON pode estar desativado ou requisições automatizadas podem ser bloqueadas.

Execução: **Actions → Descobridor de Instâncias SearXNG → Run workflow**.

## Módulo 2 — Google Dorks para mídia no Drive

Gera consultas avançadas para localizar páginas do Google Drive que estejam publicamente indexadas pelo Google, nas categorias:

- Vídeos;
- Filmes;
- Séries;
- Desenhos e animações;
- Documentários.

O script `scripts/build_google_dorks.py` gera links de pesquisa para abrir no Google e um catálogo JSON em `data/google-dorks-catalog.json`.

### Como executar pelo celular

1. Abra a aba **Actions**.
2. Selecione **Google Dorks - Catálogo de mídia pública do Drive**.
3. Toque em **Run workflow**.
4. Escolha uma categoria ou **todos**.
5. Opcionalmente, informe um termo, como `astronomia`, `natureza` ou o título de uma obra.
6. Confirme **Run workflow**.
7. Ao terminar, abra `data/google-dorks-catalog.json` na branch `main`.

### Execução local

```bash
python scripts/build_google_dorks.py --category todos
python scripts/build_google_dorks.py --category filmes --term "astronomia"
```

### Limitações importantes do Google Dorks

- O módulo gera consultas e links; não consulta nem raspa automaticamente as páginas de resultados do Google.
- O Google só mostra páginas que decidiu indexar. Muitos arquivos do Drive não aparecem na pesquisa.
- Um resultado não garante que o arquivo exista, esteja compartilhado publicamente ou permita reprodução.
- Extensões citadas na pesquisa são pistas textuais, não confirmação do formato real do arquivo.
- O módulo não acessa arquivos privados, não contorna permissões e não baixa vídeos.
- Utilize somente conteúdo que você tenha autorização para acessar, reproduzir e distribuir.

Não existe API oficial gratuita de pesquisa web geral do Google neste módulo. A automação inicial prepara um catálogo de consultas sem chave de API e sem custo de API.

## Dependências

Python 3.12 ou superior. O módulo Google Dorks usa apenas a biblioteca padrão; o módulo SearXNG usa `requests`, instalado por `requirements.txt`.

## Próximas etapas

1. Executar o workflow Google Dorks e conferir o catálogo JSON.
2. Abrir algumas consultas no Google e avaliar a qualidade dos resultados.
3. Só então decidir como integrar um provedor automatizado de pesquisa.
4. Implementar validação de links públicos, metadados, cache e deduplicação.
