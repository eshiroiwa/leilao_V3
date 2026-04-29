"""AGENTE 2 — Avaliador Comparativo de Mercado (CMA).

Este pacote é INTENCIONALMENTE isolado de ``app.agents.scraper``: o AGENTE 2
recebe apenas o ``property_id`` e busca tudo que precisa via ``SupabaseService``.
Nenhum import direto de tipos do AGENTE 1 deve aparecer aqui — assim podemos
evoluir os dois agentes em paralelo sem impactos cruzados.
"""
