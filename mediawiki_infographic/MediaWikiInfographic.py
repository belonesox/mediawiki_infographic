#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Generate different SVG infographics from MediaWiki DB.
'''
import os
import sys
import MySQLdb
import math
import networkx as nx
import argparse
import tempfile 
import belonesox_tools.MiscUtils  as ut
import errno

EXCLUDED_CATS = [u'Темы']

#pylint: disable=W0107, R0201
 
def mkdir_p(path):
    """
    Create path if not exists
    """
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
    pass            

class AliasedSubParsersAction(argparse._SubParsersAction):
    """
    Hack to support aliases in arparse before python 3.0.
    """
    class _AliasedPseudoAction(argparse.Action):
        def __init__(self, name, aliases, help):
            dest = name
            if aliases:
                dest += ' (%s)' % ','.join(aliases)
            sup = super(AliasedSubParsersAction._AliasedPseudoAction, self)
            sup.__init__(option_strings=[], dest=dest, help=help)

    def add_parser(self, name, **kwargs):
        if 'aliases' in kwargs:
            aliases = kwargs['aliases']
            del kwargs['aliases']
        else:
            aliases = []

        parser = super(AliasedSubParsersAction, self).add_parser(name, **kwargs)

        # Make the aliases work.
        for alias in aliases:
            self._name_parser_map[alias] = parser
        # Make the help text reflect them, first removing old help entry.
        if 'help' in kwargs:
            help = kwargs.pop('help')
            self._choices_actions.pop()
            pseudo_action = self._AliasedPseudoAction(name, aliases, help)
            self._choices_actions.append(pseudo_action)

        return parser


def merge_dicts(*dict_args):
    '''
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    '''
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result

def get_output(scmd):
    '''
    Just get output of OS command.
    '''
    progin, progout = os.popen4(scmd)
    sout = progout.read()
    progout.close()
    return sout 

class MediaWikiInfographic(object):
    '''
    God class for all reports
    '''
    def __init__(self):
        pass
        self.conn = None 
        self.args = None
        pass
        

    def parse_cmd(self):
        """
        Parse command line options
        Should be called like
        --db talks --user talks --password talks categorygraph --excludecats "Докладчики;NeedContacts;Страницы_с_неработающими_файловыми_ссылками;Конференции;Скрытые_категории;Доклады_на_иностранных_языках" --hyperlinkprefix "http://0x1.tv/Category:" graph.svg
        """

        parser = argparse.ArgumentParser()
        parser.register('action', 'parsers', AliasedSubParsersAction)
        parser.add_argument('--db', help='MediaWiki DB name')
        parser.add_argument('--user', help='MediaWiki DB user')
        parser.add_argument('--password', help='MediaWiki DB user pass')

        subparsers = parser.add_subparsers(dest='command', help='sub-command help')

        parser_init = subparsers.add_parser('categorygraph', help='generate SVG graph for categories', aliases=['c'])
        parser_init.add_argument('--excludecats', help='Excluded categories', nargs='?')
        parser_init.add_argument('--hyperlinkprefix', help='Like http://0x1.tv/Category:', nargs='?')
        parser_init.add_argument('--background', help='Path to background SVG', nargs='?')
        parser_init.add_argument('outputsvg', help='Output SVG file')
        self.args = parser.parse_args()
        self.conn = MySQLdb.connect(host='127.0.0.1',
                                    port=3306,
                                    user=self.args.user, 
                                    passwd=self.args.password,
                                    db=self.args.db,
                                    charset='utf8')
        pass

    
    def themes_graph(self):
        '''
        '''
        excluded_cats = ''
        if self.args.excludecats:
            excluded_cats  = ('cl2.cl_to NOT IN (' 
                               +  ', '.join(['"' + cat + '"' for cat in self.args.excludecats.split(';')])
                                + ' ) ')
        excluded_cats = ut.unicodeanyway(excluded_cats)    

        curs = self.conn.cursor()
        sql = u"""
select
    CAST(
        page_title AS CHAR(200)
    ) from_cat,
    cl2.cl_to to_cat,
    count(*) howmany
from
	categorylinks cl2,
    page
LEFT JOIN categorylinks cl1 ON cl1.cl_to = page_title
where
    %(excluded_cats)s
    and cl2.cl_from = page_id
    and page_namespace = 14
GROUP BY from_cat, to_cat
        """ % vars()
        curs.execute(sql)

        graphlines = []
        rows = curs.fetchall()

        G = nx.DiGraph()
        G.add_nodes_from([row[0] for row in rows if row[0]], articles=0, totalarticles=0)
        G.add_nodes_from([row[1] for row in rows if row[1]], articles=0, totalarticles=0)
        
        for row in rows:
            G.node[row[0]]['articles'] = G.node[row[0]]['totalarticles'] = row[2]
            G.add_edge(row[0], row[1])

        cycles = nx.simple_cycles(G)
        cycles_found = False
        if cycles:
            for cycle in cycles:
                for node in cycle:
                    print node.encode('utf-8'), '->'
                print
                cycles_found  = True

        if cycles_found:
            sys.exit(1)
            print "Found cycles"

        for node in nx.topological_sort(G):
            for sc_ in G.predecessors(node):
                G.node[node]['totalarticles'] += G.node[sc_]['totalarticles']

        # nodes = set([row[0] for row in rows] + [row[1] for row in rows])
        for node in G.nodes():
            if node  not in EXCLUDED_CATS:
                url = self.args.hyperlinkprefix + "%s" % node
                art = G.node[node]['articles']
                total = G.node[node]['totalarticles']
                articles = G.node[node]['articles']
                mod = ''
                if int(articles) not in range(3, 50):
                    mod = 'fillcolor=lightpink1'
                label = '%s /%s' % (node.replace('_', ' '), art)
                fontsize = int(14 * math.log(3+int(total))) #pylint: disable=E1101
                #fontsize = int(8 * math.sqrt(1+int(total)))
                line = u'"%s" [label="%s", URL="%s", fontsize=%d, %s ];' % (node, label, url, fontsize, mod)
                graphlines.append(line)

        for edge in G.edges():
            if edge[0] not in EXCLUDED_CATS and edge[1] not in EXCLUDED_CATS:
                line = u'"%s" -> "%s"' % (edge[1], edge[0])
                graphlines.append(line)
                

        text = u'''digraph G{
            rankdir = LR;
            ransksep =1;
            node [fontname="Calibri" shape=box style=filled fillcolor=white target="_blank"];
            edge [penwidth=2 color="blue:yellow" style=dashed]

        %s    
            
            
        }
        
        ''' %  '\n'.join(graphlines)    

        tempdotname = os.path.join(tempfile.gettempdir(), 'themes-graph.dot')
        tempsvgname = os.path.join(tempfile.gettempdir(), 'themes-graph_.svg')

        with open(tempdotname, 'w') as file_:
            file_.write(text.encode('utf-8'))
            
        scmd = 'dot -Tsvg "%(tempdotname)s" > "%(tempsvgname)s"' % vars()
        scmd = 'dot -Tsvg "%(tempdotname)s" > "%(tempsvgname)s"' % vars()   
        os.system(scmd)
    
        import pkg_resources
        svgpattern = pkg_resources.resource_string('mediawiki_infographic', 'template/pattern.svg')
        if self.args.background:
            if os.path.exists(self.args.background):
                svgpattern  = open(self.args.background, 'r').read()
            else:
                print "Path '%s' does not exists!" % self.args.background

        svg_text = open(tempsvgname, 'r').read()
        svg_text = svg_text.replace('<g id="graph0"', '''
<defs>
  <pattern id="img1" patternUnits="userSpaceOnUse" width="256" height="256">
    %(svgpattern)s
  </pattern>
</defs>
<g id="graph0"
''' % vars())
        svg_text = svg_text.replace('''</title>
<polygon fill="white"''', '''</title>
<polygon fill="url(#img1)"''')
        output_dir = os.path.split(self.args.outputsvg)[0]
        if output_dir: 
            mkdir_p(output_dir)
        open(self.args.outputsvg, 'w').write(svg_text)

def mediawiki_category_graph():
    MWI = MediaWikiInfographic()
    MWI.parse_cmd()
    MWI.themes_graph()
    pass
            
if __name__ == "__main__":
    mediawiki_category_graph()
    pass
