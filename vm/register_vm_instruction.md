

# 📘 RegisterVM 指令集说明文档

本虚拟机采用寄存器架构，支持整数运算、数组、流程控制、函数调用等功能。

---

## ✅ 通用语法格式

INSTRUCTION arg1 arg2 ...

参数可以是：
- 常量值（如 5, -1）
- 寄存器名（如 a, result）
- 数组名或标签名（如 nums, loop_start）

---

## 🧮 算术与逻辑运算

MOV r x           ; 将值 x（寄存器或常量）赋给寄存器 r <br/>
ADD r a b         ; r = a + b  <br/>
SUB r a b         ; r = a - b  <br/>
MUL r a b         ; r = a * b  <br/>
DIV r a b         ; r = a / b（向下取整）<br/>
MOD r a b         ; r = a % b  <br/>
NEG r x           ; r = -x <br/>

EQ r a b          ; r = (a == b) ? 1 : 0  <br/>
GT r a b          ; r = (a > b) ? 1 : 0  <br/>
LT r a b          ; r = (a < b) ? 1 : 0  <br/>
AND r a b         ; r = (a && b) ? 1 : 0  <br/>
OR r a b          ; r = (a || b) ? 1 : 0  <br/>
NOT r x           ; r = !x <br/>

---

## 📦 数组操作

ARR_INIT name size        ; 初始化数组  <br/>
ARR_SET name i v          ; 设置数组第 i 项为 v <br/>
ARR_GET r name i          ; 获取数组第 i 项赋给 r <br/>
LEN r name                ; r = 数组长度 <br/>

---

## 🔁 控制流

```
LABEL name                ; 定义标签   
JMP name                  ; 跳转到标签
JZ cond label             ; cond 为 0 跳转到 label

IF cond
  ...                     ; cond 非 0 执行
ELSE
  ...                     ; cond 为 0 执行
ENDIF

WHILE cond
  ...                     ; cond 为真时循环
ENDWHILE

BREAK                     ; 跳出当前 WHILE
```

---

## 🧠 函数调用

```
FUNC name
  ARG r1                  ; 函数参数（通过 PARAM 提供）
  ...
  RETURN x
ENDFUNC

PARAM x                  ; 设置函数参数（先于 CALL）
CALL name                ; 调用函数
RESULT r                 ; 获取返回值到寄存器 r
```

---

## 📤 输出与调试

```
PRINT r                  ; 输出寄存器值
DUMP                     ; 打印寄存器和数组状态
```

---

## 📝 示例：数组求和 + 平方函数调用

```
ARR_INIT nums 3
ARR_SET nums 0 2
ARR_SET nums 1 4
ARR_SET nums 2 6
MOV total 0
MOV i 0
LEN len nums

LABEL loop
LT cond i len
JZ cond end
ARR_GET x nums i
ADD total total x
ADD i i 1
JMP loop
LABEL end
PRINT total

PARAM 5
CALL square
RESULT squared
PRINT squared

FUNC square
  ARG n
  MUL result n n
  RETURN result
ENDFUNC
```
