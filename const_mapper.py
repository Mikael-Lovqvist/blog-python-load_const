import ast, inspect, textwrap, sys

#TODO - provide a method to cause an exception for references not found at the time of optimization (this requires a way to determine if a data path belongs or not, such as "startswith")
#NOTE - current version is not compatible with super() due to missing __class__ cell

#NOTE - potential future problem, currently if you call a constant, since it briefly exists as a str you'll get a syntaxwarning (SyntaxWarning: 'str' object is not callable; perhaps you missed a comma?)
#		Future versions of python may not allow this at all and we may need to do some other shenanigans in order to work around this

class cached_property:
	def __init__(self, getter):
		self.getter = getter

	def __set_name__(self, target, name):
		self.name = name

	def __get__(self, instance, owner):
		if instance is None:
			return self
		else:
			value = self.getter(instance)
			setattr(instance, self.name, value)
			return value

class code_optimizer:
	def __init__(self, source_function):
		self.source_function = source_function

	@cached_property
	def function_name(self):
		return self.tree.body[0].name

	@cached_property
	def source(self):
		return textwrap.dedent(inspect.getsource(self.source_function))

	@cached_property
	def tree(self):
		return ast.parse(self.source)

	@cached_property
	def node_parent_map(self):
		return dict(self.iter_ast_parent_map(self.tree, None))

	def prepare_ast(self):
		#Note that this changes the AST
		tree = self.tree
		tree.body[0].decorator_list.clear()
		pmap = self.node_parent_map

		#Process string constants so we can differentiate between strings and canonical paths
		for node in pmap:
			if isinstance(node, ast.Constant) and isinstance(node.value, str):
				node.value = f's{node.value}'

		#Create a path map for x.y.z style references
		path_map = dict()
		for node in pmap:
			if an := self.get_attribute_path(node):
				path_map[an] = node


		#Note - we are only interested in leaf nodes (we may have issues otherwise with a broken ast).
		#	Here we will find all leaf nodes and store in leaf_set
		leaf_set = set()
		for path in sorted(path_map.keys(), key=len, reverse=True):
			for leaf in leaf_set:
				if leaf.startswith(f'{path}.'):
					break
			else:
				leaf_set.add(path)

		return tree, leaf_set


	def process_ast(self, tree, leaf_set, canonical_map, filename):
		#Convert proper entries in canonical_map to string constants
		pmap = self.node_parent_map
		for node in pmap:
			if an := self.get_attribute_path(node):

				if an in leaf_set: #and an in canonical_map:
					parent_spec = pmap[node]

					if len(parent_spec) == 3:
						parent, field, index = parent_spec
						getattr(parent, field)[index] = ast.Constant(f'c{an}')

					elif len(parent_spec) == 2:
						parent, field = parent_spec

						setattr(parent, field, ast.Constant(f'c{an}'))


		return compile(ast.fix_missing_locations(tree) , filename, 'exec')


	def execute_definition(self, code, canonical_map, f_globals, f_locals):
		exec(code, f_globals, f_locals)
		function = f_locals[self.function_name]

		def translate_constant(const):
			if isinstance(const, str):
				code, value = const[0], const[1:]

				if code == 'c':
					return canonical_map[value]
				elif code == 's':
					return value
				else:
					raise Exception(const)
			else:
				return const

		function.__code__ = function.__code__.replace(co_consts = tuple(translate_constant(value) for value in function.__code__.co_consts))
		return function

	def get_attribute_path(self, node):
		#Only for load context
		if isinstance(node, ast.Attribute):
			if isinstance(node.ctx, ast.Load):
				if pp := self.get_attribute_path(node.value):
					return f'{pp}.{node.attr}'

		elif isinstance(node, ast.Name):
			if isinstance(node.ctx, ast.Load):
				return node.id


	@classmethod
	def iter_ast_parent_map(cls, node, parent):
		yield node, parent

		for name, field in ast.iter_fields(node):
			if isinstance(field, ast.AST):
				yield from cls.iter_ast_parent_map(field, (node, name))

			elif isinstance(field, list):
				for index, item in enumerate(field):
					if isinstance(item, ast.AST):
						yield from cls.iter_ast_parent_map(item, (node, name, index))



	def optimize(self, canonical_map, frame_offset=0, data_path_condition=None):
		frame = sys._getframe(1 + frame_offset)
		filename = frame.f_globals['__file__']
		tree, leaf_set = self.prepare_ast()

		if data_path_condition:
			leaf_set = {dp for dp in leaf_set if data_path_condition(dp)}
			#If we have a data_path_condition the assumption is that dp must be in canonical_map
			for dp in leaf_set:
				assert dp in canonical_map

		else:
			#If there is no data_path_condition the assumption is that membership of canonical_map decides if const substition should occur
			leaf_set &= set(canonical_map)

		processed_ast = self.process_ast(tree, leaf_set, canonical_map, filename)
		return self.execute_definition(processed_ast, canonical_map, frame.f_globals, frame.f_locals)

class decorator_for_canonical_map:
	def __init__(self, canonical_map, data_path_condition=None):
		self.canonical_map = canonical_map
		self.data_path_condition = data_path_condition

	def __call__(self, function):
		return code_optimizer(function).optimize(self.canonical_map, 1, data_path_condition=self.data_path_condition)
