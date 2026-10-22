import os

import pandas as pd
from py2neo import Graph, Node


class MedicalGraph:
    def __init__(self):
        self.graph = Graph("neo4j://localhost:7687", auth=("neo4j", os.environ["NEO4J_PASSWORD"]))

    @staticmethod
    def read_nodes():
        departments, diseases, symptoms, disease_information = [], [], [], []
        department_relationship, symptoms_relationship, accompany_relationship, category_relationship = [], [], [], []

        file = "./data/medical.csv"
        dataframe = pd.read_csv(file, encoding="utf-8")
        dataframe.drop(['S.No.'], axis=1, inplace=True)

        for i, row in dataframe.iterrows():
            diseases_dictionary = {}
            disease_name = row['Name']
            diseases_dictionary['name'] = disease_name
            diseases.append(disease_name)
            diseases_dictionary['description'] = ''
            diseases_dictionary['prevention'] = ''
            diseases_dictionary['causes'] = ''
            diseases_dictionary['symptoms'] = ''
            diseases_dictionary['accompany'] = ''
            diseases_dictionary['cure_department'] = ''
            diseases_dictionary['cure_way'] = ''

            symptom_temporary = row['Symptoms'].replace('[', '').replace(']', '').replace("'", '').split(",")
            symptoms = symptoms + symptom_temporary
            for symptom in symptoms:
                symptoms[symptoms.index(symptom)] = symptom.strip()
            for symptom in symptom_temporary:
                symptom = symptom.strip()
                symptoms_relationship.append([disease_name, symptom])

            accompany_temporary = row['Accompany'].replace('[', '').replace(']', '').replace("'", '').split(",")
            for accompany in accompany_temporary:
                accompany = accompany.strip()
                accompany_relationship.append([disease_name, accompany])

            diseases_dictionary['description'] = row['Description']
            diseases_dictionary['prevention'] = row['Prevention']
            diseases_dictionary['causes'] = row['Causes']

            cure_department = row['Cure Department'].replace('[', '').replace(']', '').replace("'", '').split(",")
            for item in cure_department:
                cure_department[cure_department.index(item)] = item.strip()

            if len(cure_department) == 1:
                category_relationship.append([disease_name, cure_department[0]])

            if len(cure_department) == 2:
                big = cure_department[0]
                small = cure_department[1]
                department_relationship.append([small, big])
                category_relationship.append([disease_name, small])

            diseases_dictionary['cure_department'] = cure_department
            departments = departments + cure_department

            diseases_dictionary['cure_way'] = row['Cure Way'].replace('[', '').replace(']', '').replace("'", '').split(
                ",")
            for cure_way in diseases_dictionary['cure_way']:
                diseases_dictionary['cure_way'][diseases_dictionary['cure_way'].index(cure_way)] = cure_way.strip()

            disease_information.append(diseases_dictionary)

        return set(departments), set(symptoms), set(
            diseases), disease_information, department_relationship, symptoms_relationship, accompany_relationship, category_relationship

    def create_node(self, label, nodes):
        for node_name in nodes:
            node = Node(label, name=node_name)
            self.graph.create(node)

    def create_diseases_nodes(self, disease_information):
        for disease_dictionary in disease_information:
            node = Node(
                "Disease",
                name=disease_dictionary['name'],
                description=disease_dictionary['description'],
                prevention=disease_dictionary['prevention'],
                causes=disease_dictionary['causes'],
                cure_department=disease_dictionary['cure_department'],
                cure_way=disease_dictionary['cure_way']
            )
            self.graph.create(node)

    def create_graph_nodes(self):
        departments, symptoms, diseases, disease_information, department_relationship, symptoms_relationship, accompany_relationship, category_relationship = self.read_nodes()

        self.create_diseases_nodes(disease_information)
        self.create_node("Department", departments)
        self.create_node("Symptom", symptoms)

    def create_relationship(self, start_node, end_node, edges, relationship_type, relationship_name):
        set_edges = []

        for edge in edges:
            set_edges.append('###'.join(edge))

        for edge in set(set_edges):
            edge = edge.split('###')
            p = edge[0]
            q = edge[1]
            query = "match(p:%s),(q:%s) where p.name='%s'and q.name='%s' create (p)-[rel:%s{name:'%s'}]->(q)" % (start_node, end_node, p, q, relationship_type, relationship_name)
            try:
                self.graph.run(query)
            except Exception as e:
                print(e)

    def create_graph_relationship(self):
        departments, symptoms, diseases, disease_information, department_relationship, symptoms_relationship, accompany_relationship, category_relationship = self.read_nodes()

        self.create_relationship('Department', 'Department', department_relationship, 'belongs_to', 'belong')
        self.create_relationship('Disease', 'Symptom', symptoms_relationship, 'has_symptom', 'symptom')
        self.create_relationship('Disease', 'Disease', accompany_relationship, 'accompany_with', 'complication')
        self.create_relationship('Disease', 'Department', category_relationship, 'disease_belongs_to', 'department')

    def export_data(self):
        departments, symptoms, diseases, disease_information, department_relationship, symptoms_relationship, accompany_relationship, category_relationship = self.read_nodes()

        f_department = open("./dictionary/departments.txt", 'w+', encoding="utf-8")
        f_symptom = open("./dictionary/symptoms.txt", 'w+', encoding="utf-8")
        f_disease = open("./dictionary/diseases.txt", 'w+', encoding="utf-8")

        f_department.write('\n'.join(list(departments)))
        f_symptom.write('\n'.join(list(symptoms)))
        f_disease.write('\n'.join(list(diseases)))

        f_department.close()
        f_symptom.close()
        f_disease.close()


if __name__ == '__main__':
    handler = MedicalGraph()
    handler.create_graph_nodes()
    handler.create_graph_relationship()
    handler.export_data()
