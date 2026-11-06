# OIO-SEARCH-ENGINE

Motor independente de descoberta e pesquisa para os projetos OIO.

## Etapa 1 — Descobridor de instâncias SearXNG

O primeiro workflow consulta a lista pública de instâncias mantida pelo projeto searx.space, testa até 30 endereços HTTPS e verifica se cada instância aceita uma pesquisa de teste em JSON.

### O que é registrado

- URL pública da instância;
- horário do teste;
- código HTTP e tempo de resposta;
- se a pesquisa JSON funcionou;
- quantidade de resultados retornados;
- estado e eventual erro de conexão.

O relatório é salvo em `data/searxng-instances.json`.

### Como executar

1. Abra a aba **Actions** deste repositório.
2. Se necessário, confirme **I understand my workflows, go ahead and enable them**.
3. Selecione **Descobridor de Instâncias SearXNG**.
4. Toque em **Run workflow**.
5. Opcionalmente, altere a quantidade máxima de instâncias (padrão: 30).
6. Abra a execução para acompanhar os logs. Ao terminar, consulte `data/searxng-instances.json`.

O workflow também está programado para executar diariamente às 06:17 UTC.

### Execução local

Requer Python 3.12 ou superior:

```bash
pip install -r requirements.txt
python scripts/discover_searxng.py
```

## Segurança e limites

- Não exige API key nem secrets.
- Só testa instâncias HTTPS listadas publicamente no searx.space.
- Usa uma consulta fixa e inofensiva (`SearXNG`).
- Não tenta contornar bloqueios, autenticação, CAPTCHA ou limites.
- Uma instância pública pode bloquear o GitHub Actions ou desativar JSON.
- O resultado é um diagnóstico pontual, não uma garantia de disponibilidade futura.
- O projeto registra metadados de diagnóstico; não armazena o conteúdo dos resultados de busca.

## Próximas etapas

1. Validar os resultados reais do primeiro workflow.
2. Selecionar instâncias estáveis e criar contingência.
3. Implementar o roteador de pesquisa.
4. Adicionar cache, deduplicação e API para o PWA.
