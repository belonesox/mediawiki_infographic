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
import urllib
import re

EXCLUDED_CATS = [u'Темы']
# EXCLUDED_CATS = []

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
        excluded_cats_sql = u''
        if self.args.excludecats:
            excludecat_list = ut.unicodeanyway(self.args.excludecats).split(u';')
            terms = []
            for cat in excludecat_list:
                if cat:
                    term = u"cl2.cl_to NOT LIKE '%s'" % cat 
                    terms.append(term)     
            # excluded_cats_sql  = ('cl2.cl_to NOT IN (' 
            #                    +  ', '.join(['"' + cat + '"' for cat in self.args.excludecats.split(';')])
            #                     + ' ) ')
            if terms:
                excluded_cats_sql = u'(' + u' AND '.join(terms) + u')'

        # excluded_cats = ut.unicodeanyway(excluded_cats)    

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
    %(excluded_cats_sql)s
    and cl2.cl_from = page_id
    and page_namespace = 14
GROUP BY from_cat, to_cat
        """ % vars()
        curs.execute(sql)

        graphlines = []
        rows = curs.fetchall()

        G = nx.DiGraph()
        
        excluded_cats_set = set([ut.unicodeanyway(ec) for ec in self.args.excludecats.split(';')] + EXCLUDED_CATS)
        print "\n".join(sorted(excluded_cats_set)).encode('utf-8')
        
        def banned(nd):
            nd_ = ut.unicodeanyway(nd)
            return nd_ in excluded_cats_set
        
        G.add_nodes_from([ut.unicodeanyway(row[0]) for row in rows if row[0] and not banned(row[0])], articles=0, totalarticles=0)
        G.add_nodes_from([ut.unicodeanyway(row[1]) for row in rows if row[1] and not banned(row[1])], articles=0, totalarticles=0)
        
        for row in rows:
            nd = ut.unicodeanyway(row[0])
            nd1 = ut.unicodeanyway(row[1])
            if not banned(nd):
                G.node[nd]['articles'] = G.node[nd]['totalarticles'] = row[2]
                if not banned(nd1):
                    G.add_edge(nd, nd1)

        cycles = nx.simple_cycles(G)
        cycles_found = False
        if cycles:
            print "Found cycles:"
            for cycle in cycles:
                if len(cycle) == 1:
                    G.remove_edge(cycle[0], cycle[0])
                    print "Self-loop: ", cycle[0]
                else:    
                    for node in cycle:
                        print node.encode('utf-8'), '->',
                    G.remove_edge(cycle[-1], cycle[0])
                print
                # cycles_found  = True

        if cycles_found:
            print "Found cycles"
            sys.exit(1)

        # G = nx.minimum_spanning_tree(G)

        for node in nx.topological_sort(G):
            # print "Filling node %s" % node
            for sc_ in G.predecessors(node):
                # print "  From node %s" % sc_
                G.node[node]['totalarticles'] += G.node[sc_]['totalarticles']
            # print " => ", G.node[node]['totalarticles']
            
        # nodes = set([row[0] for row in rows] + [row[1] for row in rows])

        def get_safe_unode(node):
            unode = ut.unicodeanyway(node)
            safe_unode = unode.replace('_', ' ').replace('"',r'\"')
            return safe_unode 

        for node in G.nodes():
            unode = ut.unicodeanyway(node)
            if unode  not in EXCLUDED_CATS:
                url = unicode(self.args.hyperlinkprefix) + urllib.quote(unode.encode('utf-8'))
                art = G.node[node]['articles']
                if art == 0:
                    pass
                total = int(G.node[node]['totalarticles'])
                articles = int(G.node[node]['articles'])
                mod = ''
                if articles > 50 or total < 3:
                    mod = 'fillcolor=lightpink1'
                safe_unode = get_safe_unode(unode)
                label = u'%s / %d' % (safe_unode, articles)
                fontsize = int(14 * math.log(3+int(total))) #pylint: disable=E1101
                #fontsize = int(8 * math.sqrt(1+int(total)))
                line = u'"%s" [label="%s", URL="%s", fontsize=%d, %s ];' % (safe_unode, label, url, fontsize, mod)
                graphlines.append(line)

        for edge in G.edges():
            n1 = get_safe_unode(edge[1])
            n0 = get_safe_unode(edge[0])
            if n1 not in EXCLUDED_CATS and n0 not in EXCLUDED_CATS:
                line = u'"%s" -> "%s"' % (n1, n0)
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
                svgpattern = svgpattern.replace('<?xml version="1.0" encoding="UTF-8" standalone="no"?>', '')
            else:
                print "Path '%s' does not exists!" % self.args.background

        svg_text = open(tempsvgname, 'r').read()
        svg_text = re.sub(r'<svg\s+width="\d+pt"\s+height="\d+pt"', '<svg width="1200pt" height="2000pt"', svg_text)
        svg_text = svg_text.replace('<g id="graph0"', '''
<defs>
  <pattern id="img1" patternUnits="userSpaceOnUse" width="1593" height="2656">
    %(svgpattern)s
  </pattern>
</defs>
<g id="graph0"
''' % vars())
# <polygon fill="white"''',
        for back in ['white', '#ffffff']:
            svg_text = svg_text.replace('''</title>
<polygon fill="%s"''' % back,
'''</title>
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
