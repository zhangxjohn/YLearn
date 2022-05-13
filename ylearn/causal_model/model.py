import networkx as nx
import numpy as np
from sklearn.linear_model import LinearRegression as LR

from copy import deepcopy

from .utils import check_nodes, check_ancestors_chain
from .prob import Prob
from itertools import combinations

np.random.seed(2022)


def powerset(iterable):
    """Return the power set of the iterable.

    Parameters
    ----------
    iterable : container
        Can be a set or a list.

    Returns
    ----------
    list
        The list of power set.
    """
    # TODO: return a generator instead of a list
    s = list(iterable)
    power_set = []
    for i in range(len(s) + 1):
        for j in combinations(s, i):
            power_set.append(set(j))
    return power_set


class IdentificationError(Exception):
    def __init__(self, info):
        super().__init__(self)
        self.info = info

    def __str__(self):
        return self.info


class CausalModel:
    """
    Basic object for performing causal inference.

    Attributes
    ----------
    estimator_dic : dictionary
        Keys are estimation methods while values are corresponding objects.
    estimator : estimation_learner
    causal_graph : CausalGraph #TODO: support CausalStructuralModel

    Methods
    ----------
    id(y, x, prob=None, graph=None)
        Identify the causal quantity P(y|do(x)) in the graph if identifiable
        else return False, where y can be a set of different outcomes and x
        can be a set of different treatments. #TODO: be careful about that
        currently we treat a random variable equally as its value, i.e., we
        do not discern P(Y|do(X)) and P(Y=y|do(X=x)). I don't know if this
        matters.
    identify(treatment, outcome, identify_method=None)
        Identify the causal effect of treatment on outocme expression.
    estimate(x, y, treatment, adjustment_set, quantity='ATE')
        Estimate the causal effect of treatment on outcome (y).
    identify_estimate(
        x, y, treatment, outcome, identify_method=None, quantity='ATE'
    )
        Combination of identify and estimate.
    discover_graph(data)
        Perform causal discovery over data.
    is_valid_backdoor_set(set, treatment, outcome)
        Determine if a given set is a valid backdoor adjustment set for causal
        effects of treatments on outcomes.
    get_backdoor_set(treatment, outcome, adjust='simple')
        Return backdoor adjustment sets for the given treatment and outcome
        in the style stored in adjust (simple, minimal, or all).
    get_backdoor_path(treatment, outcome)
        Return all backdoor paths in the graph between treatment and outcome.
    has_collider(path, backdoor_path=True)
        If the path in the current graph has a collider, return True, else
        return False.
    is_connected_backdoor_path(path)
        Test whether a backdoor path is connected in the current graph, where
        path[0] is the start of the path and path[-1] is the end.
    is_frontdoor_set(set, treatment, outcome)
        Determine if a given set is a frontdoor adjustment set.
    get_frontdoor_set(treatment, outcome, adjust)
        Return the frontdoor adjustment set for given treatment and outcome.
    estimate_hidden_cofounder()
        Estimation of hidden cofounders.
    """

    def __init__(self, causal_graph=None, data=None, **kwargs):
        """
        Parameters
        ----------
        causal_graph : CausalGraph
        data : DataFrame (for now)
        estimation : tuple of 2 elements
            Describe estimation methods (the first element) and machine
            learning models (the second element) used for estimation.
        """
        self.data = data
        self._adjustment_set = None
        self.treatment = None
        self.outcome = None

        # if estimation is None:
        #     # TODO: more flexible estimation, or should put this to estimate()
        #     estimation = ('LR', 'SLearner')

        # self.estimator_dic = {
        #     'SLearner': SLearner(ml_model=estimation[0]),
        #     'TLearner': TLearner(ml_model=estimation[0]),
        #     'XLearner': XLearner(ml_model=estimation[0]),
        #     'PropensityScore': PropensityScore(ml_model=estimation[0]),
        # }

        # self.estimator_dic = {'SLearner': None}

        # assert estimation[1] in self.estimator_dic.keys(), \
        #     f'Only support estimation methods in {self.estimator_dic.keys()}'

        # self.estimator = self.estimator_dic[estimation[1]]

        self.causal_graph = causal_graph if causal_graph is not None\
            else self.discover_graph(data)
        self.ava_nodes = self.causal_graph.causation.keys()

    def id(self, y, x, prob=None, graph=None):
        """Identify the causal quantity P(y|do(x)) if identifiable else return
        False. See Shpitser and Pearl (2006b)
        (https://ftp.cs.ucla.edu/pub/stat_ser/r327.pdf) for reference.
        Note that here we only consider semi-Markovian causal model, where
        each unobserved variable is a parent of exactly two nodes. This is
        because any causal model with unobserved variables can be converted
        to a semi-Markovian causal model encoding the same set of conditional
        independences (Verma, 1993).

        Parameters
        ----------
        y : set of str
            Set of outcomes.
        x : set of str
            Set of treatments.
        prob : Prob
            Probability distribution encoded in the graph.
        graph : CausalGraph or CausalStructuralModel

        Returns
        ----------
        Prob if identifiable.

        Raises
        ----------
        IdentificationError if not identifiable.
        """
        # TODO: need to be careful about the fact that set is not ordered,
        # be careful about the usage of list and set in the current
        # implementation
        if graph is None:
            graph = self.causal_graph

        if prob is None:
            prob = graph.prob

        v = set(graph.causation.keys())
        v_topo = list(graph.topo_order)

        assert y and x
        y, x = set(y), set(x)

        # 1
        if not x:
            if prob.divisor or prob.product:
                prob.marginal = v.difference(y).union(prob.marginal)
            else:
                # If the prob is not built with products, then
                # simply replace the variables with y
                prob.variables = y
            return prob

        # 2
        ancestor = graph.ancestors(y)
        prob_ = deepcopy(prob)
        if v.difference(ancestor) != set():
            an_graph = graph.build_sub_graph(ancestor)
            if prob_.divisor or prob_.product:
                prob_.marginal = v.difference(ancestor).union(prob_.marginal)
            else:
                prob_.variables = ancestor
            return self.id(y, x.intersection(ancestor), prob_, an_graph)

        # 3
        w = v.difference(x).difference(
            graph.remove_incoming_edges(x, new=True).ancestors(y)
        )
        if w:
            return self.id(y, x.union(w), prob, graph)

        # 4
        c = list(graph.remove_nodes(x, new=True).c_components)
        if len(c) > 1:
            product_expressioin = set()
            for subset in c:
                product_expressioin.add(
                    self.id(subset, v.difference(subset), prob, graph)
                )
            return Prob(
                marginal=v.difference(y.union(x)), product=product_expressioin
            )
        else:
            s = c.pop()
            cg = list(graph.c_components)
            # 5
            if cg[0] == set(graph.dag.nodes):
                raise IdentificationError(
                    'The causal effect is not identifiable in the'
                    'current graph.'
                )
            # 6
            elif s in cg:
                product_expression = set()
                for element in s:
                    product_expression.add(
                        Prob(variables={element},
                             conditional=set(v_topo[:v_topo.index(element)]))
                    )
                return Prob(
                    marginal=s.difference(y), product=product_expression
                )

            # 7
            else:
                # TODO: not clear whether directly replacing a random variable
                # with one of its value matters in this line
                for subset in cg:
                    if s.intersection(subset) == s:
                        product_expressioin = set()
                        for element in subset:
                            product_expressioin.add(
                                Prob(variables={element},
                                     conditional=set(v_topo[
                                         :v_topo.index(element)
                                     ]))
                            )
                        sub_prob = Prob(product=product_expressioin)
                        sub_graph = graph.build_sub_graph(subset)
                        return self.id(
                            y, x.intersection(subset), sub_prob, sub_graph
                        )

    def identify(self, treatment, outcome, identify_method='auto'):
        """Identify the causal effect expression.

        Parameters
        ----------
        treatment : set or list of str, optional
            Set of names of treatments.
        outcome : set or list of str, optional
            Set of names of outcomes.
        identify_method : tuple of str or str, optional. Default to 'auto'.
            Has two elements where the first one is for the identification methods
            and the second is for the returned set style.

            Available options:
            'auto' : Perform identification with all possible methods
            'general': The general identification method, see id()
            ('backdoor', 'simple'): Return a backdoor adjustment set without computation
            ('backdoor', 'minimal'): Return all possible backdoor adjustment sets with
                                     minial number of elements
            ('backdoor', 'all'): Return all possible backdoor adjustment sets
            ('frontdoor', 'simple'): Return a frontdoor adjustment set without computation
            ('frontdoor', 'minimal'): Return all possible frontdoor adjustment sets with
                                      minial number of elements
            ('frontdoor', 'all'): Return all possible backdoor adjustment sets

        Returns
        ----------
        (list, Prob) or Prob
            Prob if identify_method is ('default', 'default'), ortherwise
            return (list (the adjustment set), Prob).
        # TODO: support finding the minimal general adjustment set in linear
        # time
        """
        assert treatment and outcome, 'Please provide names of treatment and outcome'
        self.treatment = treatment
        self.outcome = outcome

        if identify_method == 'auto':
            result_dict = {
                'ID': self.id(outcome, treatment),
                'Backdoor': self.get_backdoor_set(treatment, outcome, 'simple'),
                'Frontdoor': self.get_frontdoor_set(treatment, outcome, 'simple')
            }
            return result_dict

        if identify_method == 'default':
            return self.id(outcome, treatment)

        if identify_method[0] == 'backdoor':
            adjustment = self.get_backdoor_set(
                treatment, outcome, adjust=identify_method[1]
            )
        elif identify_method[0] == 'frontdoor':
            adjustment = self.get_frontdoor_set(
                treatment, outcome, adjust=identify_method[1]
            )
        else:
            raise IdentificationError(
                'Support backdoor adjustment, frontdoor adjustment, and general'
                f'identification, but was given {identify_method[1]}'
            )

        return adjustment

    def estimate(
        self,
        estimator_model,
        data=None,
        adjustment=None,
        covariate=None,
        quantity=None,
    ):
        """Estimate the identified causal effect in new dataset.

        Parameters
        ----------
        estimator_model : EstimatorModel
            Any suitable estimator models implemented in the EstimatorModel can
            be applied here. 
        data : pandas.Dataframe, optional. Default to None
            The data set for causal effect to be estimated. If None, use the data
            which is used for discovering causal graph.
        adjustment : set or list, optional. Default to None
            Names of the adjustment set. If None, the ajustment set is given by
            the simplest backdoor set found by CausalModel.
        covariate : set or list, optional. Default to None
            Names of covariate set. Ignored if set as None.
        quantity : str, optional. Default to None
            The interested quantity when evaluating causal effects.

        Returns
        -------
        ndarray or float
            The estimated causal effect in data.
        """
        data = self.data if data is None else data

        check_nodes(self.ava_nodes, adjustment, covariate)

        assert self.outcome is not None
        assert self.treatment is not None

        outcome = self.outcome
        treatment = self.treatment

        # make sure adjustment and covariate are valid backdoor adjustment sets
        if adjustment is None and covariate is None:
            if self._adjustment_set is None:
                adjustment = self.get_backdoor_set(
                    self.treatment, self.outcome, 'simple'
                )
            else:
                adjustment = self._adjustment_set[0]
        else:
            if adjustment is not None and covariate is not None:
                temp_set = set(adjustment).union(set(covariate))
            else:
                temp_set = [set(x) for x in [adjustment, covariate] if x]
                temp_set = temp_set.pop()

            assert self.is_valid_backdoor_set(
                temp_set, self.treatment, self.outcome
            )

        # fit the estimator_model if it is not fitted
        if not estimator_model._is_fitted:
            estimator_model.fit(
                data=data,
                outcome=outcome,
                treatment=treatment,
                covariate=covariate,
                adjustment=adjustment,
            )

        effect = estimator_model.estimate(data=data, quantity=quantity)

        return effect

    # def identify_estimate(self, data, outcome, treatment, adjustment,
    #                       quantity='ATE',
    #                       condition_set=None,
    #                       condition=None,
    #                       individual=None,
    #                       identify_method=('backdoor', 'simple')):
    #     """Combination of identifiy and estimate.

    #     Parameters
    #     ----------
    #     x : DataFrame
    #         Data of the treatment.
    #     y : DataFrame
    #         Data of the outcome.
    #     treatment : str
    #         Name of the treatment.
    #     outcome : str
    #         Name of the outcome.
    #     identify_method : tuple
    #         Refer to docstring of identify().
    #     quantity : str
    #         The kind of the interested causal effect, including ATE, CATE,
    #         ITE, and CITE.

    #     Returns
    #     ----------
    #     float, optional
    #     """
    #     # TODO: now only supports estimation with adjustment set. This needs
    #     # to be updated if the estimation of general identification problem
    #     # is solved.
    #     adjustment_set = self.identify(treatment, outcome, identify_method)[0]
    #     print(f'The corresponding adjustment set is {adjustment_set}')
    #     if identify_method[1] == 'all':
    #         adjustment_set = list(adjustment_set[0])
    #     return self.estimate(
    #         data, outcome, treatment, adjustment_set, quantity, condition_set,
    #         condition, individual
    #     )

    def discover_graph(self, data):
        """Discover the causal graph from data.

        Parameters
        ----------
        data : pandas.DataFrame
        
        Returns
        ----------
        CausalGraph
        """
        assert data is not None, 'Need data to perform causal discovery.'
        raise NotImplementedError

    def is_valid_backdoor_set(self, set_, treatment, outcome):
        """Determine if a given set is a valid backdoor adjustment set for
        causal effect of treatments on the outcomes.

        Parameters
        ----------
        set_ : set
            The adjustment set.
        treatment : set or list of str
            str is also acceptable for single treatment.
        outcome : set or list of str
            str is also acceptable for single outcome.
            
        Returns
        ----------
        Bool
            True if the given set is a valid backdoor adjustment set for the 
            causal effect of treatment on outcome in the current causal graph.
        """
        # TODO: improve the implementation
        # A valid backdoor set d-separates all backdoor paths between any pairs
        # of treatments and outcomes.

        treatment = set(treatment) if type(treatment) is not str \
            else {treatment}
        outcome = set(outcome) if type(outcome) is not str else {outcome}

        # make sure all nodes are in the graph
        check_nodes(self.ava_nodes, treatment, outcome, set_)

        # build the causal graph with unobserved variables explicit
        modified_dag = self.causal_graph.remove_outgoing_edges(
            treatment, new=True
        ).explicit_unob_var_dag

        return nx.d_separated(modified_dag, treatment, outcome, set_)

    def get_backdoor_set(
        self,
        treatment,
        outcome,
        adjust='simple',
        print_info=False
    ):
        """Return the backdoor adjustment set for the given treatment and outcome.

        Parameters
        ----------
        treatment : set or list of str
            Names of the treatment. str is also acceptable for single treatment.
        outcome : set or list of str 
            Names of the outcome. str is also acceptable for single outcome.
        adjust : str
            Set style of the backdoor set
                simple: directly return the parent set of treatment
                minimal: return the minimal backdoor adjustment set
                all: return all valid backdoor adjustment set.

        Raises
        ----------
        Exception : IdentificationError
            Raise error if the style is not in simple, minimal or all or no
            set can satisfy the backdoor criterion.

        Returns
        ----------
        tuple
            The first element is the adjustment list, the second is encoded
            Prob.
        """
        # TODO: can I find the adjustment sets by using the adj matrix
        # TODO: improve the implementation

        # convert treatment and outcome to sets.
        treatment = set(treatment) if type(treatment) is not str \
            else {treatment}
        outcome = set(outcome) if type(outcome) is not str else {outcome}

        # make sure all nodes are present
        check_nodes(self.ava_nodes, outcome, treatment)

        modified_dag = self.causal_graph.remove_outgoing_edges(
            treatment, new=True
        ).explicit_unob_var_dag

        def determine(modified_dag, treatment, outcome):
            if all(
                [self.ava_nodes[t] == [] for t in treatment]
            ):
                return nx.d_separated(modified_dag, treatment,
                                      outcome, set())
            return True

        # raise exception if no set can be used as the backdoor set
        if not determine(modified_dag, treatment, outcome):
            raise IdentificationError(
                'No set can satisfy the backdoor criterion.'
            )

        # Simply take all parents of both treatment and outcome as the backdoor set
        if adjust == 'simple':
            # TODO: if the parent of x_i is the descendent of another x_j
            backdoor_list = []
            for t in treatment:
                backdoor_list += self.ava_nodes[t]
            adset = set(backdoor_list)
        # use other methods
        else:
            # Get all backdoor sets. currently implenmented
            # in a brutal force manner. NEED IMPROVEMENT
            des_set, backdoor_set_list = set(), []
            for t in treatment:
                des_set.update(
                    nx.descendants(self.causal_graph.observed_dag, t)
                )
            initial_set = (
                set(list(self.ava_nodes)) -
                treatment - outcome - des_set
            )

            if adjust == 'minimal':
                # return the backdoor set which has the fewest number of elements
                for i in powerset(initial_set):
                    if nx.d_separated(modified_dag, treatment, outcome, i):
                        backdoor_set_list.append(i)
                        break
            else:
                backdoor_set_list = [
                    i for i in powerset(initial_set)
                    if nx.d_separated(modified_dag, treatment, outcome, i)
                ]

            if not backdoor_set_list and not nx.d_separated(
                modified_dag, treatment, outcome, set()
            ):
                raise IdentificationError(
                    'No set can satisfy the backdoor criterion.'
                )

            try:
                backdoor_set_list[0]
            except Exception:
                backdoor_set_list = [[]]
            finally:
                adset = set(backdoor_set_list[0])

            if adjust == 'all':
                backdoor_list = backdoor_set_list
                self._adjustment_set = backdoor_set_list
            elif adjust == 'minimal':
                backdoor_list = backdoor_set_list[0]
            else:
                raise IdentificationError(
                    'Do not support backdoor set styles other than simple, all'
                    'or minimal.'
                )

        # Build the corresponding probability distribution.
        product_expression = {
            Prob(variables=outcome,
                 conditional=treatment.union(adset)),
            Prob(variables=adset)
        }
        prob = Prob(marginal=adset, product=product_expression)

        if print_info:
            print(
                f'The corresponding statistical estimand should be {prob.parse()})'
            )
        return (backdoor_list, prob)

    def get_backdoor_path(self, treatment, outcome):
        """Return all backdoor paths connecting treatment and outcome.

        Parameters
        ----------
        treatment : str
        outcome : str

        Returns
        ----------
        list
            A list containing all valid backdoor paths between the treatment and
            outcome in the graph.
        """
        check_nodes(self.ava_nodes, treatment, outcome)
        dag = self.causal_graph.explicit_unob_var_dag

        return [
            p for p in nx.all_simple_paths(
                dag.to_undirected(), treatment, outcome
            )
            if len(p) > 2 and p[1] in dag.predecessors(treatment)
        ]

    def has_collider(self, path, backdoor_path=True):
        """If the path in the current graph has a collider, return True, else
        return False.

        Parameters
        ----------
        path : list of str
            A list containing nodes in the path.
        backdoor_path : bool
            Whether the path is a backdoor path

        Returns
        ----------
        Boolean
            True if the path has a collider.
        """
        # TODO: improve the implementation.
        check_nodes(self.ava_nodes, path)

        if path[1] not in self.ava_nodes[path[0]]:
            backdoor_path = False

        if len(path) > 2:
            dag = self.causal_graph.explicit_unob_var_dag

            assert(nx.is_path(dag.to_undirected(), path)), "Not a valid path."

            j = 0
            if backdoor_path:
                if len(path) == 3:
                    return False

                for i, node in enumerate(path[1:], 1):
                    if node in dag.successors(path[i-1]):
                        # if path[i] is the last element, then it is impossible
                        # to have collider
                        if i == len(path) - 1:
                            return False
                        j = i
                        break
                for i, node in enumerate(path[j+1:], j+1):
                    if node in dag.predecessors(path[i-1]):
                        return True
            else:
                for i, node in enumerate(path[1:], 1):
                    if node in dag.predecessors(path[i-1]):
                        return True

        return False

    def is_connected_backdoor_path(self, path):
        """Test whether a backdoor path is connected.

        Parameters
        ----------
        path : list
            A list containing the path.

        Returns
        ----------
        Boolean
            True if path is a d-connected backdoor path and False otherwise.
        """
        check_nodes(self.ava_nodes, path)

        assert path[1] in \
            self.causal_graph.explicit_unob_var_dag.predecessors(path[0]),\
            'Not a backdoor path.'

        # A backdoor path is not connected if it contains a collider or not a
        # backdoor_path.
        # TODO: improve the implementation
        if self.has_collider(path) or \
                path not in self.get_backdoor_path(path[0], path[-1]):
            return False
        return True

    def is_frontdoor_set(self, set_, treatment, outcome):
        """True is the given set is a valid frontdoor adjustment set.

        Parameters
        ----------
        set_ : set of str
        treatement : str
        outcome : str

        Returns
        ----------
        Bool
            True if the given set is a valid frontdoor adjustment set for
            corresponding treatemtns and outcomes.
        """
        check_nodes(self.ava_nodes, set_, set(treatment), set(outcome))

        # rule 1, intercept all directed paths from treatment to outcome
        for path in nx.all_simple_paths(
            self.causal_graph.observed_dag, treatment, outcome
        ):
            if not any([path_node in set_ for path_node in path]):
                return False

        # rule 2, there is no unblocked back-door path from treatment to set_
        for subset in set_:
            for path in self.get_backdoor_path(treatment, subset):
                if self.is_connected_backdoor_path(path):
                    return False

        # rule 3, all backdoor paths from set_ to outcome are blocked by
        # treatment
        return self.is_valid_backdoor_set({treatment}, set_, {outcome})

    def get_frontdoor_set(self, treatment, outcome, adjust='simple'):
        """Return the frontdoor set for adjusting the causal effect between
        treatment and outcome.

        Parameters
        ----------
        treatment : set of str or str
            Contain only one element.
        outcome : set of str or str
            Contain only one element.

        Returns
        ----------
        tuple
            2 elements (adjustment_set, Prob)
        """
        check_nodes(self.ava_nodes, set(treatment), set(outcome))

        if type(treatment) is set and type(outcome) is set:
            assert (
                len(treatment) == 1 and len(outcome) == 1
            ), 'Treatment and outcome should be sets which contain one'
            'element for frontdoor adjustment.'
            treatment, outcome = treatment.pop(), outcome.pop()

        # Find the initial set which will then be used to generate all
        # possible frontdoor sets with the method powerset()
        initial_set = set()
        for path in nx.all_simple_paths(
            self.causal_graph.observed_dag, treatment, outcome
        ):
            initial_set.update(set(path))
        initial_set = initial_set - {treatment} - {outcome}
        potential_set = powerset(initial_set)

        # Different frontdoor set styles.
        if adjust == 'simple' or adjust == 'minimal':
            adjustment, adset = set(), set()
            for set_ in potential_set:
                if self.is_frontdoor_set(set_, treatment, outcome):
                    adjustment.update(set_)
                    adset.update(set_)
                    break
        elif adjust == 'all':
            adjustment = [
                i for i in powerset(initial_set) if self.is_frontdoor_set(
                    i, treatment, outcome
                )
            ]
            adset = adjustment[0] if adjustment else set()
        else:
            raise IdentificationError(
                'The frontdoor set style must be one of simple, all'
                'and minimal.'
            )

        if not adjustment:
            raise IdentificationError(
                'No set can satisfy the frontdoor adjustment criterion.'
            )

        # Build the corresponding probability distribution.
        product_expression = {
            Prob(variables=adset, conditional={treatment}),
            Prob(
                marginal={treatment}, product={
                    Prob(variables={outcome},
                         conditional={treatment}.union(adset)),
                    Prob(variables={treatment})
                }
            )
        }
        prob = Prob(marginal=adset, product=product_expression)
        return (adjustment, prob)

    # The following method is for experimental use
    def estimate_hidden_cofounder(self, method='lr'):
        full_dag = self.causal_graph.explicit_unob_var_dag
        cg  = deepcopy(self.causal_graph)
        all_nodes = full_dag.nodes
        hidden_cofounders = [node for node in all_nodes if "U" in node]
        estimated = 0

        def _compute_estimated(
            ob_ancestors, node, full_dag, hidden_ancestors,
        ):
            data_input = self.data[ob_ancestors]
            target = self.data[node]

            if method == "lr":
                reg = LR()
                reg.fit(data_input, target)
                predict = reg.predict(data_input)

            key_ = 'estimate_' + hidden_ancestors[0].lower()
            nodes_ = nx.descendants(full_dag, hidden_ancestors[0])
            self.data[key_] = target - predict
            modified_nodes = list(nodes_)

            edge_list_del = []
            for i in range(len(modified_nodes)):
                for j in range(i + 1, len(modified_nodes)):
                    edge_list_del.append(
                        (modified_nodes[i], modified_nodes[j])
                    )
                    edge_list_del.append(
                        (modified_nodes[j], modified_nodes[i])
                    )

            cg.remove_edges_from(edge_list=edge_list_del, observed=False)
            cg.add_nodes([key_])
            edge_list_add = [(key_, i) for i in modified_nodes]
            cg.add_edges_from(edge_list=edge_list_add)
            estimated = estimated + 1
        
        if len(hidden_cofounders) == 0:
            print('Hidden cofounder estimation done. No hidden cofounder found.')
            return

        for node in all_nodes:
            if node not in hidden_cofounders:
                ancestors = nx.ancestors(full_dag, node)
                hidden_ancestors = [
                    an for an in ancestors if an in hidden_cofounders
                ]

                if len(hidden_ancestors) == 1:
                    ob_ancestors = [
                        an for an in ancestors if an not in hidden_cofounders
                    ]
                    _check_ls = [
                        check_ancestors_chain(
                            full_dag, node, hidden_ancestors[0]
                        ) for node in ob_ancestors
                    ]
                    _true_num = sum(_check_ls)
                    if _true_num == len(ob_ancestors):
                        _compute_estimated(
                            ob_ancestors, node, full_dag, hidden_ancestors
                        )

        if estimated > 0:
            print(str(estimated) + ' hidden cofounders estimated in this turn.')
            self.estimate_hidden_cofounder(method)
        else:
            print('Hidden cofounder estimation done, and there could be ' +
                  str(len(hidden_cofounders)) + ' hidden cofounders remaining.')
            return

    def __repr__(self):
        return f'A CausalModel for {self.causal_graph}'

    