import os
import sys
import json

# JSDoc JSON schema:
#   https://github.com/jsdoc3/jsdoc/blob/master/lib/jsdoc/schema.js
# JSDoc entries used in sphinx-js:
# - optional access of [ public, private, protected ]
# - optional classdesc
# - optional comment (controls doclet inclusion)
# - optional description
# - optional exceptions
# - optional exclude-members
# -          kind of [ function, typedef, <other> ]
# -          longname
# - optional memberof
# -          meta.filename
# -          meta.lineno
# -          meta.code.paramnames
# -          meta.code.path
# -          name
# - optional params
# - optional properties
# - optional returns
# -          type.names
# - optional undocumented


class Typedoc(object):

    def get_parent(self, node):
        parentId = node.get('__parentId')
        return self.nodelist[parentId] if parentId is not None else None

    def make_longname(self, node):
        parent = self.get_parent(node)
        longname = self.make_longname(parent) if parent is not None else ""

        kindString = node.get('kindString')
        if kindString in [None, 'Function', 'Constructor', 'Method']:
            return longname
        if longname != "":
            flags = node.get('flags')
            if (parent.get('kindString') in ['Class', 'Interface'] and
                    flags.get('isStatic') is not True):
                longname += '#'
            elif parent.get('kindString') in ['Function', 'Method']:
                longname += '.'
            else:
                longname += '~'
        if kindString == 'Module':
            return longname + "module:" + node.get("name")[1:-1]
        elif kindString == 'External module':
            return longname + "external:" + node.get("name")[1:-1]
        else:
            return longname + node.get("name")

    def make_meta(self, node):
        source = node.get('sources')[0]
        return {
            'path': os.path.dirname(source.get('fileName')) or './',
            'filename': os.path.basename(source.get('fileName')),
            'lineno': source.get('line'),
            'code': {}
        }

    def extend_doclet(self, result, **kwargs):
        for name in kwargs:
            if kwargs[name] is None:
                continue
            result[name] = kwargs[name]
        return result

    def make_doclet(self, **kwargs):
        return self.extend_doclet({}, **kwargs)

    def make_type_name(self, type):
        names = []
        if type.get('type') == 'reference' and type.get('id'):
            node = self.nodelist[type.get('id')]
            # Should be: names = [ self.make_longname(node)]
            parent = self.nodelist[node.get('__parentId')]
            if parent.get('kindString') == 'External module':
                names = [parent['name'][1:-1] + "." + node['name']]
            else:
                names = [node['name']]
        elif type.get('type') in ['intrinsic', 'reference']:
            names = [type.get('name')]
        elif type.get('type') == 'stringLiteral':
            names = ['"' + type.get('value') + '"']
        elif type.get('type') == 'array':
            names = [self.make_type_name(type.get('elementType')) + '[]']
        elif type.get('type') == 'tuple':
            types = [self.make_type_name(t) for t in type.get('elements')]
            names = ['[' + ','.join(types) + ']']
        elif type.get('type') == 'union':
            types = [self.make_type_name(t) for t in type.get('types')]
            names = [' | '.join(types)]
        elif type.get('type') == 'typeOperator':
            target_name = self.make_type_name(type.get('target'))
            names = [type.get('operator'), target_name]
        elif type.get('type') == 'typeParameter':
            names = [type.get('name')]
            constraint = type.get('constraint')
            if constraint is not None:
                names.extend(["extends", self.make_type_name(constraint)])
        elif type.get('type') == 'reflection':
            names = ['<TODO>']
        return ' '.join(names)

    def make_type(self, type):
        return {
            'names': [self.make_type_name(type)]
        }

    def make_description(self, comment):
        if not comment:
            return ""
        else:
            return '\n\n'.join([
                comment.get('shortText', ''),
                comment.get('text', '')
            ])

    def make_param(self, param):
        typeEntry = param.get('type')
        if typeEntry is None:
            return self.make_doclet(
                name=param.get('name'),
                description=self.make_description(param.get('comment'))
            )
        else:
            return self.make_doclet(
                name=param.get('name'),
                type=self.make_type(typeEntry),
                description=self.make_description(param.get('comment'))
            )

    def make_result(self, param):
        type = param.get('type')
        if type is None or type.get('name') == 'void':
            return []
        return [self.make_doclet(
            name=param.get('name'),
            type=self.make_type(type),
            description=param.get('comment', {}).get('returns')
        )]

    def simple_doclet(self, kind, node):
        memberof = self.make_longname(self.get_parent(node))
        if memberof == "":
            memberof = None
        if node.get('flags').get('isPrivate'):
            access = 'private'
        elif node.get('flags').get('isProtected'):
            access = 'protected'
        else:
            access = None
        comment = node.get('comment')
        return self.make_doclet(
            kind=kind,
            access=access,
            comment=node.get('comment', {}).get('text', '<empty>'),
            meta=self.make_meta(node),
            name=node.get('name'),
            longname=self.make_longname(node),
            memberof=memberof,
            description=self.make_description(comment)
        )

    def convert_node(self, node):
        if node.get('inheritedFrom'):
            return
        if node.get('sources'):
            # Ignore nodes with a reference to absolute paths (like /usr/lib)
            source = node.get('sources')[0]
            if source.get('fileName', '.')[0] == "/":
                return

        kindString = node.get('kindString')
        if kindString == 'External module':
            doclet = self.simple_doclet('external', node)

        elif kindString == 'Module':
            doclet = self.simple_doclet('module', node)

        elif kindString in ['Class', 'Interface']:
            specifiers = []
            if kindString == 'Interface':
                doclet = self.simple_doclet('interface', node)
                specifiers.append('*interface*')
            else:
                doclet = self.simple_doclet('class', node)
            doclet['classdesc'] = ''
            if node.get('flags', {}).get('isAbstract'):
                specifiers.append('*abstract*')
            if node.get('flags', {}).get('isExported'):
                module_name = self.get_parent(node).get('name')[1:-1]
                specifiers.append('*exported from* :js:mod:`' + module_name + '`')
            doclet['classdesc'] += ', '.join(specifiers)
            if node.get('extendedTypes'):
                doclet['classdesc'] += '\n\n**Extends:**\n'
                for type in node.get('extendedTypes', []):
                    type_name = self.make_type_name(type)
                    doclet['classdesc'] += ' * :js:class:`' + type_name + '`\n'
            if node.get('implementedTypes'):
                doclet['classdesc'] += '\n\n**Implements:**\n'
                for type in node.get('implementedTypes', []):
                    type_name = self.make_type_name(type)
                    doclet['classdesc'] += ' * :js:class:`' + type_name + '`\n'

            doclet['params'] = []
            for param in node.get('typeParameter', []):
                doclet['params'].append(self.make_param(param))
            self.extend_doclet(
                doclet,
                extends=[e['name'] for e in node.get('extendedTypes', [])]
            )

        elif kindString == 'Property':
            doclet = self.simple_doclet('member', node)
            if node.get('flags', {}).get('isAbstract'):
                doclet['description'] = '*abstract*\n\n' + doclet['description']
            self.extend_doclet(
                doclet,
                type=self.make_type(node.get('type'))
            )

        elif kindString == 'Accessor':
            doclet = self.simple_doclet('member', node)
            if node.get('getSignature'):
                type = self.make_type(node['getSignature']['type'])
            else:
                type_name = node['setSignature']['parameters'][0]['type']
                type = self.make_type(type_name)
            self.extend_doclet(doclet, type=type)

        elif kindString in ['Function', 'Constructor', 'Method']:
            for sig in node.get('signatures'):
                sig['sources'] = node['sources']
                self.convert_node(sig)
            return

        elif kindString in ['Constructor signature', 'Call signature']:
            parent = self.get_parent(node)
            doclet = self.simple_doclet('function', node)
            if parent.get('flags', {}).get('isAbstract'):
                doclet['description'] = '*abstract*\n\n' + doclet['description']
            if parent.get('flags', {}).get('isOptional'):
                doclet['description'] = '*optional*\n\n' + doclet['description']
            self.extend_doclet(
                doclet,
                params=[],
                returns=self.make_result(node)
            )
            doclet['meta']['code']['paramnames'] = []
            for param in node.get('parameters', []):
                doclet['params'].append(self.make_param(param))
                doclet['meta']['code']['paramnames'].append(param.get('name'))
        else:
            doclet = None
        if doclet:
            self.jsdoc.append(doclet)
        for child in node.get('children', []):
            self.convert_node(child)

    def make_node_list(self, node, parent=None):
        if node is None:
            return
        if node.get('id') is not None:
            node['__parentId'] = parent
            self.nodelist[node['id']] = node
        for tag in ['children', 'signatures', 'parameters']:
            for child in node.get(tag, []):
                self.make_node_list(child, node.get('id'))
        typetag = node.get('type')
        if isinstance(typetag, dict) and typetag['type'] != 'reference':
            self.make_node_list(typetag, parent)
        self.make_node_list(node.get('declaration'), None)

    def __init__(self, root):
        self.jsdoc = []
        self.nodelist = {}
        self.make_node_list(root)
        self.convert_node(root)


def parse_typedoc(inputfile):
    typedoc = Typedoc(json.load(inputfile))
    return typedoc.jsdoc


def typedoc(inputname):
    with open(inputname, "r") as inputfile:
        json.dump(parse_typedoc(inputfile), sys.stdout, indent=2)


if __name__ == "__main__":
    typedoc(sys.argv[1])
