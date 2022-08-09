### Введение в РО

**Реализация РО(Роут Оптимизация) в радаро разделена на две части: RO API и RO Engine.**

Часть с апи отвечает собственно за апи, работу с бд, логику обработки различных ситуаций связанных с РО. Также я туда отношу создание входных данных для движка и обработку результатов движка(сохранение в бд, пуши).

Движок в свою очередь получает на вход данные, оптимизирует, отдает результат.

**Входные данные включают в себя**:
- **список работ**. у каждой работы могут быть следующие параметры
1) окно доставки. (Когда доставить заказ. Например, с 12:00 до 15:00. Или с полуночи до 18:00)
2) место доставки (Куда доставить, просто локация)
3) id водителя (Если водитель на работу уже назначен. и нужно только оптимально эту работу вставить)
4) объем работы (Учитывается вместимость авто водителя, чтобы работы влезли в транспорт. Никаких литров, метров кубических или килограмм нет, просто численное значение, которое определяет сам мерчант/менеджер)
5) набор скилов, необходимый для выполнения данной работы.(Используется, чтобы отсеять водителей, которые не могут выполнить работы)
6) время, затрачиваемое на месте доставки именно для этой работы. 
7) И список точек пикапа, которые нужно посетить перед тем как доставить этот заказ кастомеру. там окно времени каждого пикапа, место пикапа, объем забираемый с пикапа
- **список водителей**. У них следующие параметры 
1) Рабочий временной интервал.
2) локация начала маршрута и конца
3) вместимость транспорта
4) набор скиллов, которые может этот водитель выполнять
- дефолтное время, затрачиваемое на месте доставки
- дефолтное время, затрачиваемое на месте пикапа  
- нужно ли учитывать вместимость транспорта
- настройки для маршрутов о том что какие-то точки должны идти в начале маршрута в определенном строгом порядке. Используется в функционале рефреша маршрута, когда часть маршрута уже пройдена.

**Результаты работы движка** - массив маршрутов: водители и какие работы на них назначены в нужном порядке.

Внутри движок выполняет следующее:
- строит матрицу расстояний и времен между точками. Делается это с помощью гугл мапс directions api. Для больших РО занимает некоторое время(1-5-30 минут) и тратит некоторое количество денежек(около 50 длр на большую РО)
- Оптимизирует

**Оптимизируем с помощью библиотеки Google OR-Tools** https://developers.google.com/optimization/routing
Документация не особо хороша. Чтобы какие-то нюансы узнавать, приходится открывать исходный код на C, но чаще лазить по обсуждениям на groups google и гитхабе.
Для простого случая её использование не приносит проблем:
- указал сколько работ
- сколько водителей
- поставил ограничения (по времени работы водителей, окна доставки работам, доступные водители для работ)
- указал что минимизировать
- некоторые штрафы указал

и оптимизируй.

**Кейсы с количеством точек 400 в основном решаются достаточно хорошо.**

---

### Большая РО (400, 600, 1000, 2000 точек)

**Необходимо позволять кейсы на 600, 800, 1000 точек делать.**

**Реализован следующий алгоритм:**
- разбить большую РО на несколько более мелких РО. Например, 1000 точек разбивать на 5 по 200.
- И затем параллельно оптимизировать эти мелкие РО.

Из плюсов:
- РО на 200-300 точек часто получается решать хорошо.
- меньше времени будет тратиться, так как и перебирать вариантов нужно намного меньше 
- меньше времени тратится на построение матрицы расстояний, а также значительное сокращение потраченных на это гугл запросов и денежек.

Называем разбиение точек на более мелкие группы РО - кластеризацией.

**Кластеризация должна происходить** когда количество точек не менее 250, и количество водителей не менее 2. При меньшем количестве разбиение не имеет смысла.

При это число точек в кластерах в основном должно быть около 200 точек. Примеры(Так считается сейчас в BigClustersManager._calc_clusters_meta()):
- 500 точек - 3 кластера, минимум 133 максимум 208 точек в кластере.
- 750 точек - 4 кластера, минимум 150 максимум 234 точек в кластере.
- 800 точек - 5 кластеров, минимум 128 максимум 200 точек в кластере.
- 1000 точек - 6 кластеров, минимум 133 максимум 208 точек в кластере.

Clustering Engine на вход принимает EngineParameters, также, как и в RO Engine. Здесь происходит разбиение списка работ и списка водителей на кластеры. Ответ возвращается списком EngineParameters.

Для каждого EngineParameters запускается RO Engine.

#### Рассмотрим процесс кластеризации в Clustering Engine.

Сразу обозначим некоторые слова и их значение.
- Работа - Job/Order. Собственно полный объект работы, включает сюда точки пикапа и доставки. Обязательно имеет локацию доставки, может иметь одну или несколько пикап локаций.
- Точка - Point. Это часть работы(пикап или доставка). Если работа содержит 2 пикапа и доставку, то такая работа представляет собой 3 точки. Если только доставка - то одна точка.

**Кратко процесс состоит из 4 шагов**:
1) Первоначальная кластеризация всех работ по расположению на карте в небольшие группы(в среднем 8-13 точек в группе, но не более 70 групп в сумме).
2) Разделение некоторых из этих групп с учетом ограничений(скилл, время, назначенный водитель, географические причины).
3) Построение матрицы расстояний между этими группами, а также локациями старта/финиша водителей.
4) Итоговая кластеризация в определенное количество больших кластеров.

##### **Объяснение зачем разбивать все работы на небольшие группы(см. выше первый шаг)**.

Рассмотрим достаточно простой кейс. 800 работ. 20 водителей. Нет скиллов, нет пикапов, нет учета капасити, окна доставки большие, водители работают достаточно много, стартуют и финишируют в одном хабе, который расположен по центру между всеми работами. Например, это Минск или Варшава. Работы не имеют между собой больших различий, только расположение. Выглядит логичным желание просто использовать KMeans, скормить ему 800 локаций, и чтобы он распределил их между 5 кластерами. Всё выглядит легко и просто.

Теперь рассмотрим пример чуть сложнее. 800 работ. 18 водителей. Нет скиллов, нет пикапов, окна доставки большие, водители работают достаточно много. Но стартовые и конечные хабы расположены в различных местах, не в центре между работами, а по разным частям от работ. Также предположим что это Мельбурн и его окрестности, который находится в своей бухте. Могут быть такие расположения точек(маловероятные, но всё же), которые на карте выглядят в получасе езды на пароме, но в радаро нельзя использовать паромы при расчете расстояний. То получится что эти точки могут находиться в 4 часах езды друг от друга. KMeans не сможет учесть эти условия: 
- Количество водителей не равное на 5 кластеров, где-то должно быть меньше водителей, где-то больше. Количество работ также должно подстраиваться под это количество.
- Учесть расположение хабов, некоторые водители должны заниматься работами, которые ближе к своему хабу и не ехать в районы, где стартуют/финишируют другие водители.

**Поэтому нужен алгоритм, больше похожий на задачу о рюкзаке(нескольких рюкзаках), и не похожий на типичную задачу кластеризации, типа Kmeans.** Хотя KMeans и используется на первом шаге.

Теперь предположим что наша задача о рюкзаке имеет 800 работ плюс 18 водителей, которые нужно распределить между рюкзаками. А ещё добавим сюда скилы, капасити, окна доставки, назначенных заранее водителей, пикапы. Получим что наша задача будет более менее хорошо решаться несколько часов (со всеми ограничениями и с таким количеством элементов) (теоретически, на практике не проверял, но всё примерно так и будет). Также стоит сказать про построение матрицы расстояний - для 800 точек это 800 * 800 / 27 = 23k запросов к гуглу, что будет стоить 230USD. Для сравнения для 80 локаций это 80 * 80 / 27 = 230 запросов или 2USD.

**Поэтому необходимо уменьшить размерность задачи.** Вспомним о том что в большинстве своем работы похожи друг на друга. Давайте объединим по расположению несколько рядом стоящих работ в одну небольшую группу. Выберем центральную работу как главную, и её локация будет локацией всей группы. Будем считать что локацией каждой из работ является локация центральной работы группы.

**Таким образом мы сможем значительно сократить размерность задачи. Количество мини-групп будет не более 70. Среднее количество точек в мини-группе будет от 8 и более:**
- Немного подумав, можно прийти к тому, что такое количество точек в мини-группах с одной стороны не плодит большое число мини-групп, с другой стороны позволяет как можно меньше терять информации о работах включенных в мини-группу.
- Минимум функции о количестве запросов к гуглу на этапе кластеризации находится при среднем количестве точек в мини-группе равным (2*overall_points_count)**(1/3). Относится к случаям с 800 точками и меньше. Если точек больше, то максимальное число мини-групп ограничиваем 70.

**Шаг 1** представляет собой разбиение работ на мини-группы. Не более 70 мини-групп. Среднее количество точек в каждой мини-группе от 8. Делается это с помощью KMeans по расположению работ(именно работ, локации пикапов привязываются к ближайшим мини-группам) на карте.

На **шаге 2** происходит разделение некоторых мини-групп с учетом скиллов, доступного времени, географическим причинам(реальное время пути сильно дольше чем кажется по карте). Это происходит для того чтобы мини-группы стали более однородными внутри себя. Чтобы на **шаге 4** можно было проще и более гибко настроить ограничения и указать водителей, которые могут брать на себя данную мини-группу.

**Шаг 3** строит матрицу расстояний и времен между уже имеющимися мини-группами.

**Шаг 4** самый времязатратный, именно здесь происходит кластеризация имеющихся мини-групп и водителей в большие кластеры с учетом имеющихся ограничений, доступного времени, капасити, пикапов.

##### Подробное описание Шага 4 Кластеризации

Перед началом кластеризации случайным образом выбираются центры больших кластеров. Они будут использоваться на дальнейшем шаге, для того чтобы составить большие кластеры из мини-групп работ и водителей по отношению к этим центрам.

Используется модуль библиотеки ortools под названием cp_model. Точнее, CP-SAT Solver (https://developers.google.com/optimization/cp/cp_solver).
Код, который занимается кластеризацией мини-групп в большие группы, находится в модуле intelligent_clustering/merge.py. Там и используется cp_model.CpSolver().

Настройка солвера заключается в нескольких шагах:
- Первый шаг - Объявить переменные, которые будут использоваться во время расчетов, а также предрасчитать время/расстояние между различными мини-группами и центрами больших кластеров. 
- Второй - Настроить ограничения (минимальное/максимальное количество объектов в большом кластере, водители и мини-группы(которые могут быть в одинаковом большом кластере), ограничения по времени (то что есть у водителей и минимально необходимое на все заказы и так далее)). То есть это ограничения в которые обязательно должен попадать солвер. Их нельзя нарушать.
- Третий - Настроить objective. Это значение данного солвера, которое нужно минимизировать. Сумма различных величин, которые учитываются в зависимости от того включен тот или ной мини-кластер в большой кластер, включен тот или иной водитель в большой кластер или не включен и так далее.

Запустить решение и дождаться ответа.
Затем пересчитать новые центры больших кластеров исходя из результатов текущего разбиения.
И так далее итеративно. Количество итераций можно указывать в коде(на момент написания - 20 итераций).

Также нужно отметить что при каждом запуске солвера используется поиск "множителя времени доставки" в коде представлен просто как coefficient. Он необходим для того, чтобы балансировать кластеры по значению необходимого времени, затрачиваемого на работы кластера. А также доступного времени водителей, назначенных на данных кластер. Есть две различные ситуации, которые объясняют необходимость этого "множителя" для подгонки результатов кластеризации.
Первый. Если времени водителей недостаточно для того, чтобы развести все работы, тогда наш солвер не сможет решить задачу, так как ограничения не пропустят ни одно из решений. Для этого мы уменьшаем необходимое на доставку работ время с помощью множителя. До тех пор, пока солвер начнет давать результат.
Второй. Если времени водителей намного больше чем нужно, чтобы развести все работы. Тогда большие кластеры получатся неравномерными, так как работы в основном будут у водителей, которые ближе всего к работам. Поэтому мы увеличиваем множитель, чтобы время на доставку стало впритык с доступным временем водителей.

Также стоит отметить случай с использованием капасити. А именно, когда капасити водителей недостаточно, чтобы вместить все работы. Тогда включается дополнительная кластеризация результатов, чтобы минимизировать потери работ, а также сделать результаты хорошо выглядящими на карте и в жизни.