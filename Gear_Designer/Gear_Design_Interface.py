import itertools
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import data
import graphics_generator as gg
import ctypes

ctypes.windll.shcore.SetProcessDpiAwareness(0)
floatnumber = 4
gear_figure = None
gear_canvas = None
animation_figure = None
animation_canvas = None
animation_widget = None
animation_instance = None
animation_lines = ()
animation_line_data = ()
animation_frame = 0
animation_frame_offset = 0

def reset():
    M, T, a, d, s, ap, f = 1, 20, 1, 1.25, 1, 20, 0.236
    data.table(M, T, a, d, s, ap, f, floatnumber)

def hide_entry2():
    entry2.place_forget()
    entry2_Label.config(text=' ')

def show_entry2():
    entry2.place(x=first, y=60)
    entry2_Label.config(text='輸入齒輪模數:')

def show_data(n):
    in_data = data.get_data(n, 2, 3)
    in_text = "\n".join([f"{in_data[i]} {in_data[i+1]}" for i in range(0, len(in_data), 2)])
    in_data_label.config(text=in_text)
    
    out_data = data.get_data(n, 5, 10)
    out_text = "\n".join([f"{out_data[i]} {out_data[i+1]}" for i in range(0, len(out_data), 2)])
    out_data_label.config(text=out_text)

def toggle_buttons():
    for btn in buttons:
        if btn.winfo_viewable():
            btn.place_forget()
            show_main()
        else:
            btn.place(x=second, y=150 + buttons.index(btn) * 30)

def confirm_main():
    T, M = int(entry1.get()), float(entry2.get())
    a, d, s, ap, f = [data.get_value(2, i) for i in range(4, 13, 2)]
    data.table(M, T, a, d, s, ap, f, floatnumber)
    show_data(1)
    refresh_gear()

def show_main():
    show_data(1)
    entry1_Label.config(text='輸入齒輪齒數:')
    show_entry2()
    entry1.delete(0, tk.END)
    tk.Button(root, text="確定", command=confirm_main).place(x=first, y=confirm_y)

def show_Advanced(n):
    Label_name = ['輸入齒頂倍率:', '輸入齒根倍率:', '輸入齒間倍率:', '輸入壓力角度:', '輸入齒根圓角倍率:']
    
    def confirm():
        g = [data.get_value(3, 2), data.get_value(2, 2)] + [data.get_value(2, i) for i in range(4, 13, 2)] + [floatnumber]
        g[n + 2] = float(entry1.get())
        data.table(*g)
        show_data(n + 2)
        refresh_gear()
    
    entry1.delete(0, tk.END)
    show_data(n + 2)
    entry1_Label.config(text=Label_name[n])
    hide_entry2()
    tk.Button(root, text="確定", command=confirm).place(x=first, y=confirm_y)

def refresh_gear():
    if gear_figure is None or gear_canvas is None:
        return
    plt.figure(gear_figure.number)
    gg.graphic()
    gear_canvas.draw()
    refresh_animation()

def show_gear():
    global gear_figure, gear_canvas
    if gear_figure is None:
        gear_figure = plt.figure(linewidth=1, figsize=(5, 5))
        gear_canvas = FigureCanvasTkAgg(gear_figure, master=root)
        gear_canvas.get_tk_widget().place(x=380, y=50)
    refresh_gear()

def show_animate():
    global animation_figure, animation_canvas, animation_widget
    global animation_instance

    if animation_instance is not None:
        return

    animation_figure = plt.figure(linewidth=1, figsize=(2.2, 2.2))
    animation_canvas = FigureCanvasTkAgg(animation_figure, master=root)
    animation_widget = animation_canvas.get_tk_widget()
    animation_widget.place(x=50, y=350)
    refresh_animation()

    def update_animation(frame):
        global animation_frame
        animation_frame = frame
        angle = (frame - animation_frame_offset) / 10.0
        for line, (theta, radius) in zip(animation_lines, animation_line_data):
            line.set_data(theta + angle, radius)
        return animation_lines

    def initialize_animation():
        for line, (theta, radius) in zip(animation_lines, animation_line_data):
            line.set_data(theta, radius)
        return animation_lines

    animation_instance = animation.FuncAnimation(
        animation_figure,
        update_animation,
        frames=itertools.count(),
        interval=40,
        init_func=initialize_animation,
        blit=True,
        cache_frame_data=False,
    )
    animation_canvas.draw()


def refresh_animation():
    global animation_lines, animation_line_data, animation_frame_offset
    if animation_figure is None or animation_canvas is None:
        return

    animation_frame_offset = animation_frame
    plt.figure(animation_figure.number)
    gg.graphic()
    axes = animation_figure.axes[0]
    axes.set_axis_off()
    animation_lines = tuple(axes.lines)
    animation_line_data = tuple(
        (line.get_xdata().copy(), line.get_ydata().copy())
        for line in animation_lines
    )
    animation_canvas.draw_idle()


def stop_animation():
    global animation_figure, animation_canvas, animation_widget
    global animation_instance
    global animation_lines, animation_line_data

    if animation_instance is not None:
        animation_instance.event_source.stop()
        animation_instance = None
    if animation_widget is not None:
        animation_widget.destroy()
        animation_widget = None
    if animation_figure is not None:
        plt.close(animation_figure)
        animation_figure = None
    animation_canvas = None
    animation_lines = ()
    animation_line_data = ()


def close_interface():
    stop_animation()
    plt.close("all")
    root.destroy()


# ===========================================================================
# 初始化Tkinter主窗口
root = tk.Tk()
root.title("齒輪計算工具")
root.geometry('1000x600')
root.resizable(False, False)
root.protocol("WM_DELETE_WINDOW", close_interface)

# 初始化變量
first, second, confirm_y = 50, 200, 90

# 重新設定初始值
reset()

# 創建畫布
canvas = tk.Canvas(root, width=1000, height=600)
canvas.pack()
canvas.create_line(300, 0, 300, 600, fill="gray", width=2)
canvas.create_line(50, 200, 150, 200, fill="gray", width=2)
canvas.create_line(50, 320, 250, 320, fill="gray", width=2)

# 設置按鈕
tk.Button(root, text="1.主要參數設定", command=show_main).place(x=first, y=120)
tk.Button(root, text="確定", command=confirm_main).place(x=first, y=confirm_y)

button_name = ["2.齒頂進階設定", "3.齒根進階設定", "4.齒間進階設定", "5.壓力角度調整", "6.圓角參數調整"]
buttons = [tk.Button(root, text=button_name[i], command=lambda i=i: show_Advanced(i)) for i in range(5)]
for btn in buttons:
    btn.place_forget()

tk.Button(root, text="進階設定", command=toggle_buttons).place(x=second, y=120)

# 設置輸入框和標籤
entry1_Label = tk.Label(root, text='輸入齒輪齒數:')
entry1_Label.place(x=first, y=0)
entry2_Label = tk.Label(root, text='輸入齒輪模數:')
entry2_Label.place(x=first, y=40)

entry1 = tk.Entry(root)
entry1.place(x=first, y=20)
entry2 = tk.Entry(root)
show_entry2()

# 顯示數據
in_data_label = tk.Label(root, anchor="w", justify="left")
in_data_label.place(x=first, y=160)
out_data_label = tk.Label(root, anchor="w", justify="left")
out_data_label.place(x=first, y=210)
show_data(1)

# 顯示齒輪圖像
show_gear()
show_animate()

root.mainloop()
