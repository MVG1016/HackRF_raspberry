import socket
import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore, QtGui

# Настройки подключения
IP = '0.0.0.0'
PORT = 5000

# Создание приложения
app = QtWidgets.QApplication([])
win = QtWidgets.QWidget()
layout = QtWidgets.QVBoxLayout()
win.setLayout(layout)

# Создаем GraphicsLayout для графиков
graphics_layout = pg.GraphicsLayoutWidget(title="HackRF Live Spectrum")
layout.addWidget(graphics_layout)

# Добавляем кнопку для включения/выключения maxHold
max_hold_button = QtWidgets.QPushButton("Включить Max Hold")
max_hold_button.setCheckable(True)
layout.addWidget(max_hold_button)

# Основной график спектра
plot = graphics_layout.addPlot(title="Спектр в реальном времени")
curve = plot.plot(pen='y')  # Желтый цвет для реального спектра
max_hold_curve = plot.plot(pen='r')  # Красный цвет для max hold (изначально пустой)

plot.setLabel('bottom', 'Частота', units='Hz')
plot.setLabel('left', 'Мощность', units='dB')

# Фиксированный диапазон частот
start_freq = 1e9  # 1 ГГц
end_freq = 6e9  # 6 ГГц
frequencies = np.linspace(start_freq, end_freq, 1000)
powers = np.zeros_like(frequencies)
max_hold_powers = np.full_like(frequencies, -np.inf)  # Инициализируем с -inf вместо 0

# Устанавливаем диапазон частот на оси X
plot.setXRange(start_freq, end_freq)

# Маркеры для максимальной мощности
max_marker = pg.TextItem(anchor=(0.5, 0), color='y')  # Желтый для реального спектра
plot.addItem(max_marker)

max_hold_marker = pg.TextItem(anchor=(0.5, 0), color='r')  # Красный для max hold
plot.addItem(max_hold_marker)
max_hold_marker.hide()  # Скрываем маркер max hold изначально

# Флаг для отслеживания состояния max hold
max_hold_active = False


def toggle_max_hold(checked):
    """Включение/выключение режима max hold"""
    global max_hold_active, max_hold_powers

    max_hold_active = checked

    if max_hold_active:
        max_hold_button.setText("Выключить Max Hold")
        max_hold_marker.show()
        # Инициализируем текущими значениями при первом включении
        if np.all(max_hold_powers == -np.inf):
            max_hold_powers[:] = powers
    else:
        max_hold_button.setText("Включить Max Hold")
        max_hold_marker.hide()
        max_hold_powers[:] = -np.inf  # Сброс значений


max_hold_button.toggled.connect(toggle_max_hold)


def update_plot():
    """Обновляем график с новыми данными"""
    if len(powers) > 0:
        curve.setData(frequencies, powers)

        # Находим индекс максимальной мощности
        max_index = np.argmax(powers)
        max_freq = frequencies[max_index]
        max_power = powers[max_index]

        # Обновляем маркер с максимальной мощностью
        max_marker.setText(f"Текущий макс: {max_freq / 1e6:.2f} MHz\n{max_power:.2f} dB")
        max_marker.setPos(max_freq, max_power)

        # Обновляем max hold если режим активен
        if max_hold_active:
            # Обновляем max hold значения (берем максимум между текущими и новыми значениями)
            max_hold_powers[:] = np.maximum(max_hold_powers, powers)
            max_hold_curve.setData(frequencies, max_hold_powers)

            # Обновляем маркер для max hold
            max_hold_index = np.argmax(max_hold_powers)
            max_hold_freq = frequencies[max_hold_index]
            max_hold_pwr = max_hold_powers[max_hold_index]

            max_hold_marker.setText(f"Max Hold: {max_hold_freq / 1e6:.2f} MHz\n{max_hold_pwr:.2f} dB")
            max_hold_marker.setPos(max_hold_freq, max_hold_pwr)


# Остальной код остается без изменений...
# [Остальная часть кода остается такой же, как в предыдущем примере]

# Слушаем соединение
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((IP, PORT))
sock.listen(1)
print(f"Ожидание подключения от Raspberry Pi на {IP}:{PORT}...")
conn, addr = sock.accept()
print(f"Подключено: {addr}")

# Таймер на обновление графика (каждые 200 мс)
timer = QtCore.QTimer()
timer.timeout.connect(update_plot)
timer.start(200)

# Чтение потока данных
buffer = b''
try:
    win.show()  # Показываем окно после установки соединения

    while True:
        data = conn.recv(8192)  # Принимаем данные от Raspberry Pi
        if not data:
            break
        buffer += data
        lines = buffer.split(b'\n')
        buffer = lines[-1]  # Неполная строка на потом

        # Проверим, что нам приходит
        print(f"Received data chunk: {len(data)} bytes")

        # Парсинг данных
        new_frequencies = []
        new_powers = []

        for line in lines[:-1]:
            try:
                line_str = line.decode()  # Декодируем строку
                print(f"Line received: {line_str}")  # Отладка
                if line_str.startswith('#'):
                    continue  # Пропускаем комментарии
                parts = line_str.strip().split(',')
                if len(parts) < 7:
                    continue  # Пропускаем неполные строки
                freq_start = float(parts[2])  # Начальная частота
                bin_width = float(parts[4])  # Ширина бина (частота)
                db_values = list(map(float, parts[6:]))  # Уровни мощности

                # Добавляем новые данные в массивы
                for i, db in enumerate(db_values):
                    # Рассчитываем частоту для этого бина
                    freq = freq_start + i * bin_width
                    if start_freq <= freq <= end_freq:
                        index = int((freq - start_freq) / (end_freq - start_freq) * len(frequencies))
                        if 0 <= index < len(frequencies):
                            new_frequencies.append(freq)
                            new_powers.append(db)

            except Exception as e:
                print(f"Error processing line: {e}")  # Вывод ошибок для отладки
                continue

        # Если новые данные получены
        if new_frequencies:
            for freq, power in zip(new_frequencies, new_powers):
                index = int((freq - start_freq) / (end_freq - start_freq) * len(frequencies))
                if 0 <= index < len(frequencies):
                    powers[index] = power  # Обновляем значение мощности на правильной частоте

            app.processEvents()  # Обрабатываем события приложения
        else:
            print(f"Waiting for complete data... Current length: {len(new_frequencies)}")

except KeyboardInterrupt:
    print("Остановлено пользователем")

finally:
    conn.close()  # Закрываем соединение
    sock.close()  # Закрываем сокет