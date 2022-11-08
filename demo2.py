from const_mapper import decorator_for_canonical_map

class demo_instance:
	def __init__(self, comment):
		self.comment = comment

	def __repr__(self):
		return f'<{self.__class__.__qualname__} `{self.comment}´>'

data_map = {
	'some.long.path.to.some.data': demo_instance('Not a literal')
}

optimizer = decorator_for_canonical_map(data_map)

@optimizer
def a_function():
	print('This function needs the following item:', some.long.path.to.some.data)

import dis

dis.dis(a_function)