import socket
import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore, QtGui
from pyqtgraph import ImageItem

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

# Добавляем кнопки управления
buttons_layout = QtWidgets.QHBoxLayout()
layout.addLayout(buttons_layout)

max_hold_button = QtWidgets.QPushButton("Включить Max Hold")
max_hold_button.setCheckable(True)
buttons_layout.addWidget(max_hold_button)

waterfall_button = QtWidgets.QPushButton("Включить Waterfall")
waterfall_button.setCheckable(True)
buttons_layout.addWidget(waterfall_button)

# Основной график спектра
plot = graphics_layout.addPlot(title="Спектр в реальном времени", row=0, col=0)
curve = plot.plot(pen='y')  # Желтый цвет для реального спектра
max_hold_curve = plot.plot(pen='r')  # Красный цвет для max hold

plot.setLabel('bottom', 'Частота', units='Hz')
plot.setLabel('left', 'Мощность', units='dB')

# Водопадный дисплей
waterfall_plot = graphics_layout.addPlot(title="Waterfall", row=1, col=0)
waterfall_plot.setLabel('bottom', 'Частота', units='Hz')
waterfall_plot.setLabel('left', 'Время', units='с')
waterfall_image = ImageItem()
waterfall_plot.addItem(waterfall_image)
waterfall_plot.hide()  # Скрываем изначально

# Настройка цветовой карты для водопада
colormap = pg.colormap.get('viridis')
waterfall_image.setLookupTable(colormap.getLookupTable())

# Фиксированный диапазон частот
start_freq = 1e9  # 1 ГГц
end_freq = 6e9  # 6 ГГц
frequencies = np.linspace(start_freq, end_freq, 1000)
powers = np.zeros_like(frequencies)
max_hold_powers = np.full_like(frequencies, -np.inf)

# Настройки водопада
waterfall_history = 100  # Количество сохраняемых спектров
waterfall_data = np.zeros((waterfall_history, len(frequencies)))
waterfall_ptr = 0

# Устанавливаем диапазон частот на оси X
plot.setXRange(start_freq, end_freq)
waterfall_plot.setXRange(start_freq, end_freq)
waterfall_plot.setYRange(0, waterfall_history)

# Маркеры для максимальной мощности
max_marker = pg.TextItem(anchor=(0.5, 0), color='y')
plot.addItem(max_marker)

max_hold_marker = pg.TextItem(anchor=(0.5, 0), color='r')
plot.addItem(max_hold_marker)
max_hold_marker.hide()

# Флаги состояний
max_hold_active = False
waterfall_active = True


def toggle_max_hold(checked):
    global max_hold_active
    max_hold_active = checked

    if max_hold_active:
        max_hold_button.setText("Выключить Max Hold")
        max_hold_marker.show()
        if np.all(max_hold_powers == -np.inf):
            max_hold_powers[:] = powers
    else:
        max_hold_button.setText("Включить Max Hold")
        max_hold_marker.hide()
        max_hold_powers[:] = -np.inf


def toggle_waterfall(checked):
    global waterfall_active, waterfall_ptr, waterfall_data
    waterfall_active = checked

    if waterfall_active:
        waterfall_button.setText("Выключить Waterfall")
        waterfall_plot.show()
        # Сброс данных водопада при включении
        waterfall_data.fill(0)
        waterfall_ptr = 0
    else:
        waterfall_button.setText("Включить Waterfall")
        waterfall_plot.hide()


max_hold_button.toggled.connect(toggle_max_hold)
waterfall_button.toggled.connect(toggle_waterfall)


def update_plot():
    global waterfall_ptr

    if len(powers) > 0:
        # Обновление основного графика
        curve.setData(frequencies, powers)

        max_index = np.argmax(powers)
        max_freq = frequencies[max_index]
        max_power = powers[max_index]

        max_marker.setText(f"Текущий макс: {max_freq / 1e6:.2f} MHz\n{max_power:.2f} dB")
        max_marker.setPos(max_freq, max_power)

        # Обновление max hold
        if max_hold_active:
            max_hold_powers[:] = np.maximum(max_hold_powers, powers)
            max_hold_curve.setData(frequencies, max_hold_powers)

            max_hold_index = np.argmax(max_hold_powers)
            max_hold_freq = frequencies[max_hold_index]
            max_hold_pwr = max_hold_powers[max_hold_index]

            max_hold_marker.setText(f"Max Hold: {max_hold_freq / 1e6:.2f} MHz\n{max_hold_pwr:.2f} dB")
            max_hold_marker.setPos(max_hold_freq, max_hold_pwr)

        # Обновление водопада
        if waterfall_active:
            # Добавляем новые данные
            waterfall_data[waterfall_ptr, :] = powers
            waterfall_ptr = (waterfall_ptr + 1) % waterfall_history

            # Устанавливаем изображение с правильными координатами
            tr = QtGui.QTransform()
            tr.translate(start_freq, 0)
            tr.scale((end_freq - start_freq) / len(frequencies), 1)
            waterfall_image.setTransform(tr)

            # Обновляем данные изображения
            waterfall_image.setImage(waterfall_data.T,
                                     autoLevels=False,
                                     levels=(-100, 0))


# [Остальная часть кода остается без изменений...]


# Слушаем соединение
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((IP, PORT))
sock.listen(1)
print(f"Ожидание подключения от Raspberry Pi на {IP}:{PORT}...")
conn, addr = sock.accept()
print(f"Подключено: {addr}")

# Таймер на обновление графика
timer = QtCore.QTimer()
timer.timeout.connect(update_plot)
timer.start(200)

# Чтение потока данных
buffer = b''
try:
    win.show()

    while True:
        data = conn.recv(8192)
        if not data:
            break
        buffer += data
        lines = buffer.split(b'\n')
        buffer = lines[-1]

        new_frequencies = []
        new_powers = []

        for line in lines[:-1]:
            try:
                line_str = line.decode()
                if line_str.startswith('#'):
                    continue
                parts = line_str.strip().split(',')
                if len(parts) < 7:
                    continue
                freq_start = float(parts[2])
                bin_width = float(parts[4])
                db_values = list(map(float, parts[6:]))

                for i, db in enumerate(db_values):
                    freq = freq_start + i * bin_width
                    if start_freq <= freq <= end_freq:
                        index = int((freq - start_freq) / (end_freq - start_freq) * len(frequencies))
                        if 0 <= index < len(frequencies):
                            new_frequencies.append(freq)
                            new_powers.append(db)

            except Exception as e:
                print(f"Error processing line: {e}")
                continue

        if new_frequencies:
            for freq, power in zip(new_frequencies, new_powers):
                index = int((freq - start_freq) / (end_freq - start_freq) * len(frequencies))
                if 0 <= index < len(frequencies):
                    powers[index] = power

            app.processEvents()

except KeyboardInterrupt:
    print("Остановлено пользователем")

finally:
    conn.close()
    sock.close()