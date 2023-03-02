"""
Программа для ассинхронного доступа к текущей погоде в городах указанный в файле city.txt.
В результаты выполнения выводится средняя, минимальная и максимальная температура.
"""

import selectors
import socket
from urllib.parse import urlsplit
import json
from operator import itemgetter


list_of_ready_gen = []  # Список генероторов готовых к запуску
current_gen = None  # Текущий генеротор
main_selector = selectors.DefaultSelector()

PORT = 80

results_from_sites = []     # Список данных полученных от сайта


def parse_response(response: str):
    """
    Разбор принятой от сайта строки данных

    :param response: строка данных принятая от сайта
    :return: кортеж формата ('Название города', Температура)
    """

    if len(response) == 0:
        print('На разбор данных была принята пуста строка')
        return None

    rows = response.split("\r\n")
    try:
        if rows[0].find('200') == -1:
            response_error = rows[0].split(' ')[1]
            print('Сервер вернул ошибку - ', response_error)
            return None
    except IndexError:
        print('Приняты некорректные данные от сайта')
        return None

    try:
        response_json = json.loads(rows[-1])
        return (response_json['location']['name'], response_json['current']['temp_c'])
    except Exception as e:
        print('Ошибка при формировании json из данных полученных от сервера - ', str(e))
        return None


def analiz_results() -> None:
    """
    Анализ данных полученных от сайта
    """

    if len(results_from_sites) == 0:
        print('В результате работы не были получены данные')
        return

    clean_result = []
    parsed_result = list(map(parse_response, results_from_sites))

    for res in parsed_result:
        if res is not None:
            clean_result.append(res)

    if len(clean_result) == 0:
        print('Все ответы полученные от сервера с ошибкой')
        return

    clean_result = sorted(clean_result, key=itemgetter(1))
    sum_temp = sum([x[1] for x in clean_result])
    max_temp = clean_result[-1]
    min_temp = clean_result[0]
    print(f'''
    Средняя температура в указанных городах на данный момент: {format(sum_temp/len(clean_result), ".3g")} C
    Максимальная: {format(max_temp[1], ".2g")} C, город - {max_temp[0]} 
    Минимальная: {format(min_temp[1], ".2g")} C, город - {min_temp[0]}
    ''')


def loop(main_gen):
    """
    Цикл событий, управляет запуском сопрограм.
    Ждет событий на файловых объектах привязанных к сокетам
    """

    create_task(main_gen)
    while True:
        while list_of_ready_gen:
            run_gen(list_of_ready_gen.pop(0))

        if not main_selector.get_map():
            analiz_results()
            return

        events = main_selector.select()
        for key, mask in events:
            main_selector.unregister(key.fileobj)
            gen = key.data['gen']
            run_gen(gen, key, mask)


def create_task(gen):
    """
    Добавление генератора в список на выполнение

    :param gen: Генератор
    """

    list_of_ready_gen.append(gen)


def run_gen(gen, key=None, mask=None):
    """
    Запуск сопрограммы

    :param gen: генератор на запуск
    :param key: экземпляр SelectorKey, соответствует файловому объекту
    :param mask: битовая маска событий, готовых для этого файлового объекта
    :return:
    """

    global current_gen
    current_gen = gen
    try:
        if key:
            current_gen.send((key, mask))
        else:
            next(gen)
    except StopIteration:
        pass


def wait_for(fileobj, data=None, events=selectors.EVENT_READ | selectors.EVENT_WRITE):
    """
    Регистрирование файлового объекта для отслеживания его на предмет событий ввода/вывода

    :param fileobj: Файловый объект для мониторинга
    :param data: Данные для формирования строки на отправку и принятия данных
    :param events: Вид отслеживаемых событий
    """

    main_selector.register(fileobj, events, {'gen': current_gen, 'data': data})


def generate_url(city: str) -> str:
    """
    Генерация url

    :param city: Название города
    :return: корректный url
    """

    city = ''.join(filter(lambda char: char.isalpha(), city))
    return f'http://api.weatherapi.com/v1/current.json?key=0a6586359d6e4c3084c73940232802&q={city.title()}&aqi=no'


def open_connection():
    """
    Создание сокетов, на каждый город создается свой сокет
    """

    try:
        gen_for_file = (line for line in open('city.txt'))
    except IOError:
        print('Ошибка при открытии файла city.txt')
        return

    for i, city in enumerate(gen_for_file):
        url_split = urlsplit(generate_url(city))
        addr = (url_split.netloc, PORT)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)

        try:
            sock.connect_ex(addr)
        except Exception as e:
            print(f'Ошибка при выполнении socket.connect_ex - {str(e)}')
            return

        events = selectors.EVENT_WRITE
        msg = f'GET {url_split.path}?{url_split.query} HTTP/1.0\n' \
              'Host: api.weatherapi.com\n\n'.encode()
        data = {
            'i': i,
            'msg': msg,
            'msg_size': len(msg),
            'recv_total': 0,
            'recv_msg': b'',
            'out_b': b''
        }
        wait_for(sock, data, events)


def service_connection(key, mask):
    """
    Чтение и запись данных через файловый объект привязанный к сокету.
    Вызывается только когда сокет готов принимать либо передавать данные.

    :param key: экземпляр SelectorKey, соответствует файловому объекту
    :param mask: битовая маска событий, готовых для этого файлового объекта
    """

    pack_size = 1024
    while True:
        sock = key.fileobj
        data = key.data['data']
        if mask & selectors.EVENT_READ:
            try:
                recv_data = sock.recv(pack_size)
            except ConnectionError:
                print(f"Ошибка при приеме данных")
                break
            if recv_data:
                data['recv_total'] += len(recv_data)
                data['recv_msg'] += recv_data
            if not recv_data:
                results_from_sites.append(data['recv_msg'].decode())
                sock.close()
                break
            else:
                key, mask = yield wait_for(sock, data, selectors.EVENT_READ)

        if mask & selectors.EVENT_WRITE:
            if not data['out_b'] and data['msg']:
                data['out_b'] = data['msg']
                data['msg'] = False
            if data['out_b']:
                try:
                    sent = sock.send(data['out_b'])
                except ConnectionError:
                    print(f"Ошибка при передаче данных")
                    break
                data['out_b'] = data['out_b'][sent:]
                key, mask = yield wait_for(sock, data, selectors.EVENT_READ)


def main():

    open_connection()

    while True:
        key, mask = yield
        create_task(service_connection(key, mask))


if __name__ == "__main__":
    loop(main())

