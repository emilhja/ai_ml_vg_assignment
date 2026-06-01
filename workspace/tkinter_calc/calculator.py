import tkinter as tk

class Calculator:
    def __init__(self, master):
        self.master = master
        master.title("Calculator")

        self.total = 0
        self.current = ""
        self.input_value = True
        self.check_sum = False
        self.op = ""
        self.result = False

        # Display
        self.display = tk.Entry(master, font=('arial', 20, 'bold'),
                                bg='powder blue', bd=30, justify='right')
        self.display.grid(row=0, column=0, columnspan=4, pady=1)
        self.display.insert(0, "0")

        num_pad = ['7', '8', '9', '4', '5', '6', '1', '2', '3', '0', '.', '+-', ]

        # Number buttons"
        i = 0
        btn = []
        for j in range(2, 6):
            for k in range(3):
                btn.append(tk.Button(master, height=2, width=4,
                                     font=('arial', 20, 'bold'),
                                     bd=4, text=num_pad[i]))
                btn[i].grid(row=j, column=k, pady=1)
                btn[i]["command"] = lambda store_num=num_pad[i]: self.number_press(store_num)
                i += 1

        # Operator buttons
        self.create_operator_button("C", 1, 0, self.clear_entry)
        self.create_operator_button("CE", 1, 1, self.clear_all)
        self.create_operator_button("sqrt", 1, 2, self.sqrt)
        self.create_operator_button("+", 2, 3, lambda: self.operation("+"))
        self.create_operator_button("-", 3, 3, lambda: self.operation("-"))
        self.create_operator_button("*", 4, 3, lambda: self.operation("*"))
        self.create_operator_button("/", 5, 3, lambda: self.operation("/"))
        self.create_operator_button("=", 5, 2, self.sum_of_total)


    def create_operator_button(self, text, row, col, command):
        button = tk.Button(self.master, height=2, width=4,
                           font=('arial', 20, 'bold'), bd=4, text=text,
                           bg='powder blue', command=command)
        button.grid(row=row, column=col, pady=1)

    def number_press(self, num):
        self.result = False
        firstnum = self.display.get()
        secondnum = str(num)
        if self.input_value:
            self.current = secondnum
            self.input_value = False
        else:
            if secondnum == '.':
                if secondnum in firstnum:
                    return
            self.current = firstnum + secondnum
        self.display.delete(0, tk.END)
        self.display.insert(0, self.current)

    def operation(self, op):
        self.current = float(self.current)
        if self.check_sum == True:
            self.sum_of_total()
        elif not self.result:
            self.total = self.current
            self.input_value = True
        self.check_sum = True
        self.op = op
        self.result = False
        self.display.delete(0, tk.END)
        self.display.insert(0, str(self.total))

    def sum_of_total(self):
        self.result = True
        self.input_value = True
        if self.check_sum == True:
            self.current = float(self.current)
            if self.op == "+":
                self.total += self.current
            elif self.op == "-":
                self.total -= self.current
            elif self.op == "*":
                self.total *= self.current
            elif self.op == "/":
                self.total /= self.current
            else:
                self.total = self.current
            self.check_sum = False
            self.display.delete(0, tk.END)
            self.display.insert(0, self.total)
        
    def clear_all(self):
        self.display.delete(0, tk.END)
        self.display.insert(0, "0")
        self.total = 0
        self.current = ""
        self.input_value = True
        self.check_sum = False
        self.op = ""
        self.result = False

    def clear_entry(self):
        self.display.delete(0, tk.END)
        self.display.insert(0, "0")
        self.input_value = True

    def sqrt(self):
        self.current = float(self.display.get())
        if self.current < 0:
            self.display.delete(0, tk.END)
            self.display.insert(0, "Error")
            return
        self.current = self.current ** 0.5
        self.display.delete(0, tk.END)
        self.display.insert(0, str(self.current))
        self.total = self.current
        self.input_value = True


if __name__ == '__main__':
    root = tk.Tk()
    app = Calculator(root)
    root.mainloop()