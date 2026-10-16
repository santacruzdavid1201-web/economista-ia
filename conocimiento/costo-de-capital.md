---
titulo: "Costo de capital (WACC): con qué tasa descontar un proyecto"
temas: [WACC, costo de capital, costo promedio ponderado, tasa de descuento, con qué tasa descontar, costo del patrimonio, lo que exigen los dueños, CAPM, beta, prima de riesgo, riesgo país, TES, costo de la deuda, Hamada, costo de los activos, tasa real, tasa nominal]
fuente: Elaboración propia con base en Damodaran (Applied Corporate Finance) y Brealey, Myers y Allen (Principios de finanzas corporativas)
revisado: true
---
El costo de capital es la rentabilidad mínima que debe dar una inversión para
pagarles a quienes la financian lo que exigen por el riesgo que corren: los
bancos (deuda) y los dueños (patrimonio). También es un costo de oportunidad:
lo que esa misma plata ganaría en otra inversión de riesgo parecido.

El costo de capital promedio ponderado (WACC) mezcla los dos costos según
cuánto pone cada uno:

WACC = P / (D + P) × Ke + D / (D + P) × Kd × (1 − t)

En palabras: la parte que ponen los dueños multiplicada por lo que ellos
exigen, más la parte que ponen los bancos multiplicada por lo que cobran
después del ahorro de impuestos, porque los intereses se descuentan de la
renta. D es la deuda financiera, P el patrimonio y t la tarifa de renta. En una
pyme se usan los valores en libros, porque no tiene precio en bolsa. Lo que
cobran los bancos (Kd) sale de los gastos financieros del año entre la deuda
financiera promedio.

Esa es la fórmula en pesos corrientes (nominal). Para descontar flujos en
pesos de hoy, todo va en términos reales: el ahorro de impuestos se calcula
sobre el interés nominal, que es el que se deduce de la renta, y después se le
quita la inflación del año:

Kd real = (1 + Kd × (1 − t)) / (1 + inflación) − 1

En palabras: 1 más la tasa de la deuda después de impuestos, dividido entre 1
más la inflación del año, menos 1. El WACC real mezcla el Ke real con ese Kd
real, con los mismos pesos de deuda y patrimonio.

Lo que exigen los dueños (Ke) se estima con el modelo CAPM:

Ke = tasa sin riesgo + β × prima de riesgo

En palabras: lo que paga una inversión sin riesgo (en Colombia, el TES menos
el spread de incumplimiento, como se explica abajo), más una prima por el
riesgo del negocio. La beta (β) mide cuánto se mueve el negocio con el mercado: 1 es
como el promedio; menos de 1, menos. Una pyme no cotiza en bolsa, así que se
usa la beta de su sector y se ajusta a su propia deuda con la fórmula de
Hamada: β con deuda = β sin deuda × (1 + (1 − t) × D / P). Más deuda, más
riesgo para los dueños, y más exigen.

En Colombia el bono del gobierno (TES) no está libre de riesgo: paga un spread
por el riesgo de que el país no pague. El método de Damodaran le resta ese
spread al TES y suma el riesgo país dentro de la prima de las acciones,
multiplicado por la beta. Sumar la prima completa al TES completo contaría el
riesgo país dos veces. El TES en UVR ya es una tasa real; las primas de
Damodaran se miden en dólares, y aplicarlas a una tasa real en pesos es una
aproximación.

Real o nominal: los flujos y la tasa van en la misma moneda. Flujos en pesos
de hoy se descuentan con una tasa real; flujos en pesos corrientes, con una
tasa nominal. Se pasa de una a otra con la ecuación de Fisher:
(1 + nominal) = (1 + real) × (1 + inflación). Descontar flujos en pesos de hoy
con una tasa nominal subvalora el proyecto: le descuenta una inflación que sus
flujos no traen.

Sin deuda, el costo de capital es el de los activos: lo que el mercado le
exige a un negocio del sector solo por su riesgo. Cuando no hay estados
financieros para calcular el WACC, se muestra como referencia, no como el WACC
de la empresa.

Cuándo sirve: el WACC es la tasa adecuada para un proyecto con el mismo riesgo
del negocio de siempre y que se financia con la misma mezcla de deuda y
patrimonio. A un proyecto más riesgoso (un negocio nuevo, otra ciudad) se le
puede exigir más. Además, el CAPM supone un inversionista diversificado: el
dueño de una pyme que tiene casi todo su patrimonio en la empresa corre más
riesgo del que mide la beta, y es razonable que exija más que el WACC.

Si el proyecto deja un VPN positivo descontado con el WACC, rinde más de lo
que cuesta su capital: paga lo que exigen los dueños y los bancos y además
deja un excedente.
