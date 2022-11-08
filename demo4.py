import ast, inspect

def a_function():
	print('This function needs the following item:', some.long.path.to.some.data)

print(ast.dump(ast.parse(inspect.getsource(a_function), mode='exec'), indent=2))