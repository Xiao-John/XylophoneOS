-- Minimal self-test shipped with the Lua package.
local function fib(n)
  if n < 2 then return n end
  return fib(n - 1) + fib(n - 2)
end

print(_VERSION)
print("fib(10)=" .. fib(10))

local squares = {}
for i = 1, 5 do squares[i] = i * i end
print("squares=" .. table.concat(squares, ","))
print("fmt=" .. string.format("%s/%d/%.2f", "xos", 42, 3.5))
