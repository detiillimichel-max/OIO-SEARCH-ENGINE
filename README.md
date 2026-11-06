# OIO-SEARCH-ENGINE

Motor independente de descoberta e pesquisa para os projetos OIO.

## Módulo 1 — Descobridor de instâncias SearXNG

O workflow consulta a lista pública mantida pelo projeto searx.space, testa instâncias HTTPS e verifica se aceitam pesquisa em JSON.

Relatório: `data/searxng-instances.json`.

O teste inicial encontrou 83 endereços HTTPS e 0 respostas JSON válidas no ambiente do GitHub Actions. Isso não prova que todas estejam offline: JSON pode estar desativado ou requisições automatizadas podem ser bloqueadas.

## Módulo 2 — Google Dorks para mídia no Drive

Gera consultas avançadas para localizar páginas do Google Drive publicamente indexadas pelo Google: vídeos, filmes, séries, desenhos e documentários.

Script: `scripts/build_google_dorks.py`.
Relatório de consultas: `data/google-dorks-catalog.json`.

O módulo gera links para abrir no Google; ele não coleta automaticamente os resultados do Google. Um resultado não garante que o arquivo esteja público, reproduzível ou autorizado para retransmissão.

## Módulo 3 — OIO Media Player PWA

Interface web/PWA em `player/` com:

- Pesquisa por título, descrição e tags.
- Filtros para filmes, séries, desenhos e documentários.
- Catálogo com capas/miniaturas quando fornecidas.
- Player incorporado por pré-visualização oficial do Google Drive.
- Reprodução HTML5 somente para fontes diretas marcadas como autorizadas e compatíveis.
- Botão de tela cheia.
- Botão de próximo episódio para itens com o mesmo `series_id`.
- Manifest e service worker para instalação/cache básico no Android.

### Abrir o player

Depois de habilitar GitHub Pages para a branch `main`, abra:

`https://detiillimichel-max.github.io/OIO-SEARCH-ENGINE/player/`

O catálogo está em `data/drive-media.json`. Ele começa vazio intencionalmente. Para adicionar um item, use este formato:

```json
{
  "schema_version": 1,
  "updated_at": null,
  "items": [
    {
      "title": "Título autorizado",
      "url": "https://drive.google.com/file/d/ID_DO_ARQUIVO/view",
      "category": "series",
      "series_id": "serie-exemplo",
      "episode": "S01E01",
      "poster": "https://exemplo.org/capa.jpg",
      "tags": ["exemplo"],
      "description": "Descrição",
      "authorized": true
    }
  ]
}
```

Categorias aceitas: `filmes`, `series`, `desenhos`, `documentarios`.

Para reprodução HTML5 direta, use `"playback_type": "direct"` e `"authorized": true` somente quando a origem fornecer uma URL de mídia compatível e houver autorização. Links do Drive usam `/preview`; o funcionamento depende das permissões e das políticas de incorporação do Google.

### Atualização do catálogo

Workflow: **Actions → Atualizar catálogo OIO Media**.

Executa manualmente ou a cada 12 horas. Valida o JSON, remove URLs duplicadas e atualiza o timestamp. Não pesquisa o Google nem descobre novos arquivos automaticamente; a descoberta automática dependerá de um provedor de busca permitido e de uma fonte de resultados integrada.

## Segurança, direitos e limitações

- Não acesse arquivos privados nem tente contornar permissões, CAPTCHA ou bloqueios.
- Utilize somente conteúdo que você tenha autorização para acessar, reproduzir e distribuir.
- Ter um link público ou indexado não significa ter direito de retransmissão.
- O player não baixa nem hospeda vídeos; usa a pré-visualização da origem ou uma URL direta autorizada.
- A disponibilidade, o codec, o CORS e as regras do provedor podem impedir a reprodução.

## Dependências

Python 3.12 ou superior. Google Dorks usa a biblioteca padrão; o módulo SearXNG usa `requests`, instalado por `requirements.txt`.


## Módulo 4 — OIO Auto Publisher

Workflow: **Actions → OIO Auto Publisher**. Executa a cada 10 minutos (horário UTC do GitHub; o Python interpreta o fuso `America/Sao_Paulo`) ou manualmente.

O motor seleciona lotes variáveis a partir de `data/publication-queue.json` e `data/content-pool.json`, evita IDs já publicados e atualiza `data/social-feed.json`. O padrão de lotes de demonstração é 100, 50, 70, 120, 80 e 100 itens por janela, limitado ao conteúdo elegível disponível.

O player passa a ler `data/social-feed.json`. Para entrar no feed, cada item precisa ter `id`, `title`, `url`, `category`, `authorized: true` e `status: "ready"`. A URL precisa ser HTTPS. Categorias do publicador: `videos`, `filmes`, `series`, `desenhos`, `documentarios`, `jornalismo` e `educacao`.

**Importante:** o motor agenda publicações de conteúdos reais do acervo. Não cria usuários, curtidas, comentários ou visualizações fictícias. O catálogo inicial está vazio; é necessário inserir conteúdo com direitos de publicação e transmissão. O workflow não faz upload nem hospeda os vídeos. O agendamento do GitHub pode sofrer atrasos e não é um relógio de transmissão em tempo real.
