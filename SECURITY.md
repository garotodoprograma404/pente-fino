# Segurança

O Pente-fino é uma ferramenta de segurança, então um furo nele (um golpe que ele não acusa, ou um arquivo que o faz travar) merece cuidado.

**Achou uma amostra que passa batido?** Não abra uma issue pública com ela: isso entrega o contorno pra todo mundo antes da regra existir. Use o **aviso privado de segurança** do GitHub (aba *Security* → *Report a vulnerability*). Pode mandar a pasta de teste inofensiva (só `echo`, nunca carga de verdade).

O que acontece depois: a regra nova entra, o teste que a prova entra junto e o seu nome vai pro histórico de mudanças (se você quiser).

O que a gente trata como bug de segurança:
- o pente-fino **executar** algo da pasta analisada (ele só lê);
- o pente-fino **travar** ou **cair** com um arquivo feito pra isso;
- a saída ser **enganada** (um arquivo apagar ou reescrever o próprio aviso de perigo);
- um golpe documentado (Microsoft, Trend Micro, Elastic…) que ele deveria acusar e não acusa.

O que **não** é bug: código malicioso "comum", que só roda quando você executa o programa. O pente-fino não é antivírus (veja o README).
