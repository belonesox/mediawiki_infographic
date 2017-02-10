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
        parser_init.add_argument('outputsvg', help='Output SVG file')
        self.args = parser.parse_args()
        self.conn = MySQLdb.connect(host='localhost',
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
        curs.execute(u"""
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
        """ % vars())

        graphlines = []
        rows = curs.fetchall()

        G = nx.DiGraph()
        G.add_nodes_from([row[0] for row in rows if row[0]], articles=0, totalarticles=0)
        G.add_nodes_from([row[1] for row in rows if row[1]], articles=0, totalarticles=0)
        
        for row in rows:
            G.node[row[0]]['articles'] = G.node[row[0]]['totalarticles'] = row[2]
            G.add_edge(row[0], row[1])

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
        print scmd    
        os.system(scmd)
    
        svg_text = open(tempsvgname, 'r').read()
        svg_text = svg_text.replace('<g id="graph0"', '''
<defs>
  <pattern id="img1" patternUnits="userSpaceOnUse" width="256" height="256">
    <svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><path d="M-26,-142L142,-127L234,-124Z" fill="#b8e1b5" stroke="#b8e1b5" stroke-width="1.51"/><path d="M202,371L106,391L347,365Z" fill="#1f7b3c" stroke="#1f7b3c" stroke-width="1.51"/><path d="M303,351L202,371L347,365Z" fill="#0f7132" stroke="#0f7132" stroke-width="1.51"/><path d="M234,-124L309,-108L358,-100Z" fill="#89ba8d" stroke="#89ba8d" stroke-width="1.51"/><path d="M343,296L347,365L363,198Z" fill="#0f7433" stroke="#0f7433" stroke-width="1.51"/><path d="M358,-100L300,-7L387,-20Z" fill="#75a978" stroke="#75a978" stroke-width="1.51"/><path d="M300,-7L352,49L387,-20Z" fill="#69a56d" stroke="#69a56d" stroke-width="1.51"/><path d="M347,116L363,198L387,-20Z" fill="#4b9353" stroke="#4b9353" stroke-width="1.51"/><path d="M352,49L347,116L387,-20Z" fill="#5b9b60" stroke="#5b9b60" stroke-width="1.51"/><path d="M343,296L303,351L347,365Z" fill="#026e2d" stroke="#026e2d" stroke-width="1.51"/><path d="M317,103L347,116L352,49Z" fill="#519d59" stroke="#519d59" stroke-width="1.51"/><path d="M309,-108L300,-7L358,-100Z" fill="#7fb383" stroke="#7fb383" stroke-width="1.51"/><path d="M273,269L343,296L363,198Z" fill="#1a813d" stroke="#1a813d" stroke-width="1.51"/><path d="M280,189L273,269L363,198Z" fill="#288e47" stroke="#288e47" stroke-width="1.51"/><path d="M347,116L280,189L363,198Z" fill="#35924b" stroke="#35924b" stroke-width="1.51"/><path d="M-26,-142L51,-122L142,-127Z" fill="#caeac5" stroke="#caeac5" stroke-width="1.51"/><path d="M317,103L280,189L347,116Z" fill="#449b53" stroke="#449b53" stroke-width="1.51"/><path d="M288,56L317,103L352,49Z" fill="#5ba562" stroke="#5ba562" stroke-width="1.51"/><path d="M300,-7L288,56L352,49Z" fill="#67aa6d" stroke="#67aa6d" stroke-width="1.51"/><path d="M273,269L303,351L343,296Z" fill="#137a37" stroke="#137a37" stroke-width="1.51"/><path d="M216,-39L300,-7L309,-108Z" fill="#83bc88" stroke="#83bc88" stroke-width="1.51"/><path d="M234,-124L216,-39L309,-108Z" fill="#8fc494" stroke="#8fc494" stroke-width="1.51"/><path d="M288,56L223,107L317,103Z" fill="#5cac66" stroke="#5cac66" stroke-width="1.51"/><path d="M223,107L280,189L317,103Z" fill="#4ca55b" stroke="#4ca55b" stroke-width="1.51"/><path d="M234,31L288,56L300,-7Z" fill="#6fb476" stroke="#6fb476" stroke-width="1.51"/><path d="M226,203L273,269L280,189Z" fill="#30984e" stroke="#30984e" stroke-width="1.51"/><path d="M273,269L202,371L303,351Z" fill="#187f3b" stroke="#187f3b" stroke-width="1.51"/><path d="M216,-39L234,31L300,-7Z" fill="#7cbd82" stroke="#7cbd82" stroke-width="1.51"/><path d="M183,280L202,371L273,269Z" fill="#278d46" stroke="#278d46" stroke-width="1.51"/><path d="M223,107L226,203L280,189Z" fill="#45a65a" stroke="#45a65a" stroke-width="1.51"/><path d="M234,31L223,107L288,56Z" fill="#69b571" stroke="#69b571" stroke-width="1.51"/><path d="M226,203L183,280L273,269Z" fill="#30984f" stroke="#30984f" stroke-width="1.51"/><path d="M223,107L153,217L226,203Z" fill="#4aae60" stroke="#4aae60" stroke-width="1.51"/><path d="M153,217L183,280L226,203Z" fill="#3ea559" stroke="#3ea559" stroke-width="1.51"/><path d="M145,32L223,107L234,31Z" fill="#74c27c" stroke="#74c27c" stroke-width="1.51"/><path d="M216,-39L145,32L234,31Z" fill="#83c888" stroke="#83c888" stroke-width="1.51"/><path d="M142,-127L216,-39L234,-124Z" fill="#9ad19f" stroke="#9ad19f" stroke-width="1.51"/><path d="M183,280L133,312L202,371Z" fill="#34934b" stroke="#34934b" stroke-width="1.51"/><path d="M106,98L153,217L223,107Z" fill="#65bb6d" stroke="#65bb6d" stroke-width="1.51"/><path d="M142,-127L112,-34L216,-39Z" fill="#a1d6a2" stroke="#a1d6a2" stroke-width="1.51"/><path d="M145,32L106,98L223,107Z" fill="#7ac67d" stroke="#7ac67d" stroke-width="1.51"/><path d="M112,-34L145,32L216,-39Z" fill="#96d195" stroke="#96d195" stroke-width="1.51"/><path d="M133,312L106,391L202,371Z" fill="#3a8e4a" stroke="#3a8e4a" stroke-width="1.51"/><path d="M153,217L133,312L183,280Z" fill="#44a258" stroke="#44a258" stroke-width="1.51"/><path d="M51,-122L112,-34L142,-127Z" fill="#b7e1b3" stroke="#b7e1b3" stroke-width="1.51"/><path d="M55,285L133,312L153,217Z" fill="#54a960" stroke="#54a960" stroke-width="1.51"/><path d="M59,201L55,285L153,217Z" fill="#62b56d" stroke="#62b56d" stroke-width="1.51"/><path d="M106,98L59,201L153,217Z" fill="#6dc074" stroke="#6dc074" stroke-width="1.51"/><path d="M112,-34L35,30L145,32Z" fill="#a2d99d" stroke="#a2d99d" stroke-width="1.51"/><path d="M35,30L106,98L145,32Z" fill="#97d492" stroke="#97d492" stroke-width="1.51"/><path d="M20,352L-59,384L106,391Z" fill="#619a65" stroke="#619a65" stroke-width="1.51"/><path d="M55,285L20,352L106,391Z" fill="#5aa060" stroke="#5aa060" stroke-width="1.51"/><path d="M56,98L59,201L106,98Z" fill="#84cb83" stroke="#84cb83" stroke-width="1.51"/><path d="M48,-28L35,30L112,-34Z" fill="#b2e0ab" stroke="#b2e0ab" stroke-width="1.51"/><path d="M55,285L106,391L133,312Z" fill="#509e59" stroke="#509e59" stroke-width="1.51"/><path d="M35,30L56,98L106,98Z" fill="#99d694" stroke="#99d694" stroke-width="1.51"/><path d="M51,-122L48,-28L112,-34Z" fill="#bbe3b5" stroke="#bbe3b5" stroke-width="1.51"/><path d="M-43,-48L48,-28L51,-122Z" fill="#caeac4" stroke="#caeac4" stroke-width="1.51"/><path d="M-26,-142L-43,-48L51,-122Z" fill="#d8f0d2" stroke="#d8f0d2" stroke-width="1.51"/><path d="M-9,306L20,352L55,285Z" fill="#6aab6f" stroke="#6aab6f" stroke-width="1.51"/><path d="M-62,109L-47,192L56,98Z" fill="#9ed69b" stroke="#9ed69b" stroke-width="1.51"/><path d="M-9,306L55,285L59,201Z" fill="#6fb575" stroke="#6fb575" stroke-width="1.51"/><path d="M-47,192L-9,306L59,201Z" fill="#7ec084" stroke="#7ec084" stroke-width="1.51"/><path d="M56,98L-47,192L59,201Z" fill="#89cc8b" stroke="#89cc8b" stroke-width="1.51"/><path d="M35,30L-62,109L56,98Z" fill="#a8dca2" stroke="#a8dca2" stroke-width="1.51"/><path d="M-58,35L-62,109L35,30Z" fill="#b8e3b1" stroke="#b8e3b1" stroke-width="1.51"/><path d="M-43,-48L35,30L48,-28Z" fill="#c1e7ba" stroke="#c1e7ba" stroke-width="1.51"/><path d="M-43,-48L-58,35L35,30Z" fill="#c5e8be" stroke="#c5e8be" stroke-width="1.51"/><path d="M-9,306L-59,384L20,352Z" fill="#6fa773" stroke="#6fa773" stroke-width="1.51"/><path d="M-62,109L-83,141L-47,192Z" fill="#a4d8a3" stroke="#a4d8a3" stroke-width="1.51"/><path d="M-100,202L-90,315L-47,192Z" fill="#90c795" stroke="#90c795" stroke-width="1.51"/><path d="M-47,192L-90,315L-9,306Z" fill="#83bc88" stroke="#83bc88" stroke-width="1.51"/><path d="M-90,315L-59,384L-9,306Z" fill="#79ae7c" stroke="#79ae7c" stroke-width="1.51"/><path d="M-90,315L-96,363L-59,384Z" fill="#7caa7f" stroke="#7caa7f" stroke-width="1.51"/><path d="M-137,-138L-43,-48L-26,-142Z" fill="#e6f6e1" stroke="#e6f6e1" stroke-width="1.51"/><path d="M-133,61L-62,109L-58,35Z" fill="#c1e6bb" stroke="#c1e6bb" stroke-width="1.51"/><path d="M-83,141L-100,202L-47,192Z" fill="#9dd3a0" stroke="#9dd3a0" stroke-width="1.51"/><path d="M-142,-20L-58,35L-43,-48Z" fill="#d6efcf" stroke="#d6efcf" stroke-width="1.51"/><path d="M-137,-138L-142,-20L-43,-48Z" fill="#e6f6e1" stroke="#e6f6e1" stroke-width="1.51"/><path d="M-142,-20L-133,61L-58,35Z" fill="#d0edca" stroke="#d0edca" stroke-width="1.51"/><path d="M-133,61L-83,141L-62,109Z" fill="#b7e1b2" stroke="#b7e1b2" stroke-width="1.51"/><path d="M-133,61L-100,202L-83,141Z" fill="#afddad" stroke="#afddad" stroke-width="1.51"/><path d="M-100,202L-96,363L-90,315Z" fill="#88ba8d" stroke="#88ba8d" stroke-width="1.51"/><path d="M-100,202L-133,61L-96,363Z" fill="#9acf9f" stroke="#9acf9f" stroke-width="1.51"/></svg>
  </pattern>
</defs>
<g id="graph0"
''')
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
