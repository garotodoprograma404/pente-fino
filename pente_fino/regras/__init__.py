"""As regras do pente-fino. Cada uma é uma função `verificar(arquivo) -> achados`.

Regra nova = um arquivo nesta pasta + uma linha aqui.
"""

from pente_fino.regras import agentes, binarios, editor, escondido, git, pacotes, segredos, sombra

REGRAS = (
    editor.verificar,  # o que roda ao ABRIR a pasta no editor
    git.verificar,  # o que o git executa sozinho
    agentes.verificar,  # config e instruções pra IA do editor
    pacotes.verificar,  # o que roda no npm install / pip install / cargo build
    escondido.verificar,  # o que está no arquivo mas você não vê
    segredos.verificar,  # chaves e senhas no código
    binarios.verificar,  # programa compilado e atalho pra fora
    sombra.verificar,  # arquivo que se passa por módulo do Python
)
