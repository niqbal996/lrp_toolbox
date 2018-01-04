'''
@author: Sebastian Lapuschkin
@author: Gregoire Montavon
@author: Maximilian Kohlbrenner
@maintainer: Sebastian Lapuschkin
@contact: sebastian.lapuschkin@hhi.fraunhofer.de, wojciech.samek@hhi.fraunhofer.de
@date: 14.08.2015
@version: 1.2+
@copyright: Copyright (c)  2015-2017, Sebastian Lapuschkin, Alexander Binder, Gregoire Montavon, Klaus-Robert Mueller, Wojciech Samek
@license : BSD-2-Clause
'''

import copy
import sys
import time
from module import Module

import mxnet as mx
from mxnet import nd

# -------------------------------
# Sequential layer
# -------------------------------
class Sequential(Module):
    '''
    Top level access point and incorporation of the neural network implementation.
    Sequential manages a sequence of computational neural network modules and passes
    along in- and outputs.
    '''

    def __init__(self,modules, ctx=mx.cpu()):
        '''
        Constructor

        Parameters
        ----------
        modules :   list, tuple, etc. enumerable.
                    an enumerable collection of instances of class Module

        ctx:        mxnet.context.Context
                    device used for all mxnet.ndarray operations

        '''
        Module.__init__(self)
        self.modules = modules
        self.set_context(ctx)

    def set_context(self, ctx):
        '''
        Change context of all modules. Afterwards, a forward pass is needed before a new backward / lrp call

        Parameters
        ----------
        ctx : mxnet.context.Context
            mx context (usually mx.cpu() or mx.gpu())
        '''
        self.ctx = ctx
        for m in self.modules:
            m.set_context(ctx)

    def forward(self,X):
        '''
        Realizes the forward pass of an input through the net

        Parameters
        ----------
        X : mxnet.ndarray.ndarray.NDArray
            a network input.

        Returns
        -------
        X : mxnet.ndarray.ndarray.NDArray
            the output of the network's final layer
        '''

        for m in self.modules:
            X = m.forward(X)
        return X


    def backward(self,DY):
        for m in self.modules[::-1]:
            DY = m.backward(DY)
        return DY


    def update(self,lrate):
        for m in self.modules:
            m.update(lrate)


    def clean(self):
        '''
        Removes temporary variables from all network layers.
        '''
        for m in self.modules:
            m.clean()


    def train(self, X, Y,  Xval = None, Yval = None,  batchsize = 25, iters = 10000, lrate = 0.005, lrate_decay = None, lfactor_initial=1.0 , status = 250, convergence = -1, transform = None):
        '''
        Provides a method for training the neural net (self) based on given data.

        Parameters
        ----------

        X : mxnet.ndarray.ndarray.NDArray
            the training data, formatted to (N,D) shape, with N being the number of samples and D their dimensionality

        Y : mxnet.ndarray.ndarray.NDArray
            the training labels, formatted to (N,C) shape, with N being the number of samples and C the number of output classes.

        Xval : mxnet.ndarray.ndarray.NDArray
            some optional validation data. used to measure network performance during training.
            shaped (M,D)

        Yval : mxnet.ndarray.ndarray.NDArray
            the validation labels. shaped (M,C)

        batchsize : int
            the batch size to use for training

        iters : int
            max number of training iterations

        lrate : float
            the initial learning rate. the learning rate is adjusted during training with increased model performance. See lrate_decay

        lrate_decay : string
            controls if and how the learning rate is adjusted throughout training:
            'none' or None disables learning rate adaption. This is the DEFAULT behaviour.
            'sublinear' adjusts the learning rate to lrate*(1-Accuracy**2) during an evaluation step, often resulting in a better performing model.
            'linear' adjusts the learning rate to lrate*(1-Accuracy) during an evaluation step, often resulting in a better performing model.

        lfactor_initial : float
            specifies an initial discount on the given learning rate, e.g. when retraining an established network in combination with a learning rate decay,
            it might be undesirable to use the given learning rate in the beginning. this could have been done better. TODO: do better.
            Default value is 1.0

        status : int
            number of iterations (i.e. number of rounds of batch forward pass, gradient backward pass, parameter update) of silent training
            until status print and evaluation on validation data.

        convergence : int
            number of consecutive allowed status evaluations with no more model improvements until we accept the model has converged.
            Set <=0 to disable. Disabled by DEFAULT.
            Set to any value > 0 to control the maximal consecutive number (status * convergence) iterations allowed without model improvement, until convergence is accepted.

        transform : function handle
            a function taking as an input a batch of training data sized [N,D] and returning a batch sized [N,D] with added noise or other various data transformations. It's up to you!
            default value is None for no transformation.
            expected syntax is, with X.shape == Xt.shape == (N,D)
            def yourFunction(X):
                Xt = someStuff(X)
                return Xt
        '''

        t_start = time.time()
        untilConvergence = convergence;    learningFactor = lfactor_initial
        bestAccuracy = 0.0;                bestLayers = copy.deepcopy(self.modules)
        bestLoss = sys.maxint # changed from np.inf to sys.maxint to avoid numpy import TODO: cast from numpy instead?
        bestIter = 0

        # initialize data iterator. attention: last batch is padded with part of the first batch if it smaller than batchsize
        data_iterator = mx.io.NDArrayIter(data=X, label=Y, shuffle=True, batch_size=batchsize, last_batch_handle='pad')

        if not Xval is None and not Yval is None:
            val_data_iterator = mx.io.NDArrayIter(data=Xval, label=Yval, shuffle=False, batch_size=batchsize, last_batch_handle='discard')

        N = X.shape[0]
        for d in xrange(iters):

            #the actual training:
            #first, get samples from the iterator (currently the data order is random when creating the iterator but stays the same over the batches and epochs)

            try:
                data_batch = data_iterator.next()
            except StopIteration:
                # TODO: decide whether to reshuffle the data here
                # atm: just reset the data iterator. If we wanted to reshuffle, we could as well create a new iterator but this might be less efficient.
                # print ' ... starting next epoch'
                data_iterator.hard_reset()
                data_batch = data_iterator.next()

            #transform batch data (maybe)
            if transform == None:
                batch = data_batch.data[0]
            else:
                batch = transform(data_batch.data[0])

            #forward and backward propagation steps with parameter update
            Ypred = self.forward(batch)
            batch_labels = data_batch.label[0]

            self.backward(Ypred - batch_labels) #l1-loss
            self.update(lrate*learningFactor)

            #periodically evaluate network and optionally adjust learning rate or check for convergence.
            if (d+1) % status == 0:
                if not Xval is None and not Yval is None: #if given, evaluate on validation data (comment Max: mxnet.nd array comparison to list fails, changed to comparison to None )

                    # feed the whole validation set in batches of batchsize through the network:
                    val_data_iterator.hard_reset()
                    while True:
                        try:
                            loss = nd.empty(batchsize, ctx=Xval.context)
                            accs = nd.empty(batchsize, ctx=Xval.context)

                            val_data_batch = val_data_iterator.next()
                            val_batch_data   = val_data_batch.data[0]
                            val_batch_labels = val_data_batch.label[0]
                            val_batch_pred = self.forward(val_batch_data)

                            val_batch_corr_preds = nd.argmax(val_batch_pred, axis=1) == nd.argmax(val_batch_labels, axis=1)
                            val_batch_l1loss     = nd.sum(nd.abs(val_batch_pred - val_batch_labels), axis=1)
                            # l1loss = (nd.sum(nd.abs(Ypred - Yval))/Yval.shape[0]).asscalar()

                            nd.concat(accs, val_batch_corr_preds, dim=0)
                            nd.concat(loss, val_batch_l1loss,     dim=0)

                        except StopIteration:
                            break

                    acc    = nd.mean(accs).asscalar()
                    l1loss = nd.mean(loss).asscalar()
                    print 'Accuracy after {0} iterations on validation set: {1}% (l1-loss: {2:.4})'.format(d+1, acc*100,l1loss)

                else: #evaluate on the training data only
                    Ypred = self.forward(X)
                    acc = nd.mean(nd.argmax(Ypred, axis=1) == nd.argmax(Y, axis=1)).asscalar()
                    l1loss = (nd.sum(nd.abs(Ypred - Y))/Y.shape[0]).asscalar()
                    print 'Accuracy after {0} iterations on training data: {1}% (l1-loss: {2:.4})'.format(d+1,acc*100,l1loss)


                #save current network parameters if we have improved
                #if acc >= bestAccuracy and l1loss <= bestLoss:
                # only go by loss
                if l1loss <= bestLoss:
                    print '    New loss-optimal parameter set encountered. saving....'
                    bestAccuracy = acc
                    bestLoss = l1loss
                    bestLayers = copy.deepcopy(self.modules)
                    bestIter = d

                    #adjust learning rate
                    if lrate_decay == None or lrate_decay == 'none':
                        pass # no adjustment
                    elif lrate_decay == 'sublinear':
                        #slow down learning to better converge towards an optimum with increased network performance.
                        learningFactor = 1.-(acc*acc)
                        print '    Adjusting learning rate to {0} ~ {1:.2f}% of its initial value'.format(learningFactor*lrate, learningFactor*100)
                    elif lrate_decay == 'linear':
                        #slow down learning to better converge towards an optimum with increased network performance.
                        learningFactor = 1.-acc
                        print '    Adjusting learning rate to {0} ~ {1:.2f}% of its initial value'.format(learningFactor*lrate, learningFactor*100)

                    #refresh number of allowed search steps until convergence
                    untilConvergence = convergence
                else:
                    untilConvergence-=1
                    if untilConvergence == 0 and convergence > 0:
                        print '    No more recorded model improvements for {0} evaluations. Accepting model convergence.'.format(convergence)
                        break

                t_elapsed =  time.time() - t_start
                percent_done = float(d+1)/iters #d+1 because we are after the iteration's heavy lifting
                t_remaining_estimated = t_elapsed/percent_done - t_elapsed

                m, s = divmod(t_remaining_estimated, 60)
                h, m = divmod(m, 60)
                d, h = divmod(h, 24)

                timestring = '{}d {}h {}m {}s'.format(int(d), int(h), int(m), int(s))
                print '    Estimate time until current training ends : {} ({:.2f}% done)'.format(timestring, percent_done*100)

            elif (d+1) % (status/10) == 0:
                # print 'alive' signal
                #sys.stdout.write('.')
                l1loss =  (nd.sum(nd.abs(Ypred - batch_labels))/ (1. * Ypred.shape[0])).asscalar()
                sys.stdout.write('batch# {}, lrate {}, l1-loss {:.4}\n'.format(d+1,lrate*learningFactor,l1loss)) # TODO: does the asnumpy() make it inefficient?
                sys.stdout.flush()

        #after training, either due to convergence or iteration limit
        print 'Setting network parameters to best encountered network state with {}% accuracy and a loss of {} from iteration {}.'.format(bestAccuracy*100, bestLoss, bestIter)
        self.modules = bestLayers


    def set_lrp_parameters(self,lrp_var=None,param=None):
        for m in self.modules:
            m.set_lrp_parameters(lrp_var=lrp_var,param=param)

    def lrp(self,R,lrp_var=None,param=None):
        '''
        Performs LRP by calling subroutines, depending on lrp_var and param or
        preset values specified via Module.set_lrp_parameters(lrp_var,lrp_param)

        If lrp parameters have been pre-specified (per layer), the corresponding decomposition
        will be applied during a call of lrp().

        Specifying lrp parameters explicitly when calling lrp(), e.g. net.lrp(R,lrp_var='alpha',param=2.),
        will override the preset values for the current call.

        How to use:

        net.forward(X) #forward feed some data you wish to explain to populat the net.

        then either:

        net.lrp() #to perform the naive approach to lrp implemented in _simple_lrp for each layer

        or:

        for m in net.modules:
            m.set_lrp_parameters(...)
        net.lrp() #to preset a lrp configuration to each layer in the net

        or:

        net.lrp(somevariantname,someparameter) # to explicitly call the specified parametrization for all layers (where applicable) and override any preset configurations.

        Parameters
        ----------
        R : mxnet.ndarray.ndarray.NDArray
            final layer relevance values. usually the network's prediction of some data points
            for which the output relevance is to be computed
            dimensionality should be equal to the previously computed predictions

        lrp_var : str
            either 'none' or 'simple' or None for standard Lrp ,
            'epsilon' for an added epsilon slack in the denominator
            'alphabeta' or 'alpha' for weighting positive and negative contributions separately. param specifies alpha with alpha + beta = 1
            'flat' projects an upper layer neuron's relevance uniformly over its receptive field.
            'ww' or 'w^2' only considers the square weights w_ij^2 as qantities to distribute relevances with.

        param : double
            the respective parameter for the lrp method of choice

        Returns
        -------

        R : mxnet.ndarray.ndarray.NDArray
            the first layer relevances as produced by the neural net wrt to the previously forward
            passed input data. dimensionality is equal to the previously into forward entered input data

        Note
        ----

        Requires the net to be populated with temporary variables, i.e. forward needed to be called with the input
        for which the explanation is to be computed. calling clean in between forward and lrp invalidates the
        temporary data
        '''

        for m in self.modules[::-1]:
            R = m.lrp(R,lrp_var,param)
        return R
