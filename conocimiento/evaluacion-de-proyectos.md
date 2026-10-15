---
titulo: "Evaluación de proyectos: VPN, TIR y tasa de oportunidad"
temas: [VPN, valor presente neto, TIR, tasa interna de retorno, TIRM, recuperación, payback, índice de rentabilidad, tasa de oportunidad, crear valor, evaluar un proyecto, inversión, remodelación, ampliación, sensibilidad, valor crítico, punto de quiebre, tornado, riesgo del proyecto]
fuente: Elaboración propia
revisado: false
---
Evaluar un proyecto es comparar lo que deja con lo que dejaría la misma plata
en la mejor alternativa de riesgo parecido. Esa rentabilidad de la
alternativa es la tasa de oportunidad.

El valor presente neto (VPN) trae a pesos de hoy todos los flujos del
proyecto, descontándolos con la tasa de oportunidad:

VPN = Σ F_t / (1 + i)^t

En palabras: cada flujo de caja del año t se divide entre 1 más la tasa de
oportunidad elevado a t, y se suman todos, incluida la inversión del año 0
con signo negativo. Si el VPN es positivo, el proyecto crea valor: deja más
que la alternativa. Si es negativo, no crea valor: deja menos.

La tasa interna de retorno (TIR) es la tasa con la que el VPN da cero: la
rentabilidad anual del propio proyecto. Se compara con la tasa de
oportunidad. Un proyecto con una TIR de 13 % y una tasa de oportunidad de
15 % sí rinde, pero menos que la alternativa: no crea valor, aunque no pierda
plata. Rendir y crear valor no son lo mismo.

Para decidir manda el VPN. La TIR puede no existir, puede haber varias cuando
el flujo cambia de signo más de una vez (por ejemplo, una remodelación
grande a mitad del proyecto) y puede engañar al comparar proyectos de
distinto tamaño, porque un proyecto pequeño puede tener una TIR alta y dejar
menos pesos. La TIR modificada (TIRM) corrige parte de esto: supone que lo que
deja el proyecto se reinvierte a la tasa de oportunidad y no a la TIR.

La recuperación descontada dice en cuántos años el proyecto devuelve la
inversión contando lo que esa plata habría rendido en la alternativa. El
índice de rentabilidad dice cuántos pesos de hoy devuelve el proyecto por
cada peso invertido: mayor que uno, crea valor; menor que uno, no.

Ejemplo: una inversión de 106 millones (obra y capital de trabajo) que deja
27,8 millones al año durante cuatro años y 33,8 millones el quinto, con una
tasa de oportunidad de 10 %, tiene un VPN de 3,1 millones (crea valor), una
TIR de 11,11 %, y se recupera en 4,85 años.

Los flujos que se evalúan son el flujo de caja libre del proyecto, sin la
financiación: los intereses y las cuotas del crédito no se restan, porque el
costo de la deuda ya entra en la tasa de descuento. Restarlos y además
descontar con esa tasa contaría la deuda dos veces.

La inflación entra en dos lugares. Primero en la tasa: las tasas que se
cotizan (las de los bancos, los TES, la de oportunidad) son nominales, traen
la inflación esperada adentro. Si los flujos están a precios de hoy, hay que
descontarlos con la tasa real, (1 + tasa nominal) / (1 + inflación) − 1, o,
lo que es lo mismo, descontar los flujos en pesos corrientes con la tasa
nominal. Descontar flujos a precios de hoy con una tasa nominal es el error
más común, y castiga el proyecto. Segundo, dentro del flujo: los impuestos se
pagan en pesos corrientes, la deducción por depreciación es fija en pesos de
la compra y el capital de trabajo crece con los precios, así que la inflación
le quita valor al proyecto aunque el negocio real sea el mismo.

El análisis de sensibilidad mide qué tan frágil es el resultado: se mueve
un dato a la vez (los ingresos, los costos, la inversión, la tasa de
oportunidad), con todo lo demás igual, y se ve cuánto cambia el VPN. El
gráfico de tornado ordena los datos del que más mueve el VPN al que menos. El
valor crítico de cada dato es el punto en que el VPN llega a cero: si los
ingresos pueden caer solo 3 % antes de que el proyecto deje de crear valor,
el margen es estrecho, aunque el VPN sea positivo. La tasa de oportunidad
crítica es justamente la TIR. Mover un dato a la vez no dice qué pasa si
varios salen mal al mismo tiempo; para eso sirve una simulación con rangos
para cada dato.

Crear valor es un criterio de decisión, no una recomendación: antes de hacer
un proyecto también hay que mirar su riesgo y si la empresa tiene la caja
para financiarlo.
