"""Nós do pipeline AGENTE 4.

Cada nó recebe o contexto e retorna um sub-resultado isolado. Os nós são
funções puras (sync) ou async — o orquestrador (``service.run_deep_analysis``)
faz fan-out com ``asyncio.gather`` e consolida os resultados.

* Os nós PUROS (sem I/O externo) ficam síncronos e são executados em thread
  pool quando preciso.
* Os nós com I/O (Firecrawl, Google Places, OpenAI) são ``async``.
"""
